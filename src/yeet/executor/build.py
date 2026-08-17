"""docker build for a project Dockerfile. Tag = hash(dockerfile + context) = free cache.

The whole build cache is the tag. Hash the Dockerfile and the list of files in
its context; if an image with that tag already exists locally, the build is a
no-op. No cache directory, no invalidation logic, no state to get out of sync
with reality — about fifteen lines of actual work.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yeet.core.resources import packaged_path
from yeet.executor.backend import DockerFailure, daemon_is_gone
from yeet.executor.images import BASE_IMAGE, ImageSpec

TAG_PREFIX = "yeet-local"
BASE_DOCKERFILE = "Dockerfile.base"
BASE_DOCKERFILE_ENV = "YEET_BASE_DOCKERFILE"

_PREP_LOCKS: dict[str, threading.Lock] = {}
_PREP_REGISTRY_LOCK = threading.Lock()


def _prep_lock(reference: str) -> threading.Lock:
    """One lock per image reference, created on demand.

    Jobs in a wave run in parallel threads and they very often want the SAME
    image — a five-leg matrix is five jobs and one image. Without this, all
    five discover it is missing at the same moment and all five start building
    or pulling it: the daemon serialises the work anyway, so nothing is gained,
    but the run pays for it several times over and the log interleaves five
    copies of the same build output. With it, the first thread prepares the
    image and the rest wait, then find it present and return immediately.

    Keyed by reference rather than a single global lock so that a wave needing
    two different images still prepares them concurrently.
    """
    with _PREP_REGISTRY_LOCK:
        return _PREP_LOCKS.setdefault(reference, threading.Lock())


HASH_LENGTH = 12
MAX_CONTEXT_FILES = 20_000
"""Same ceiling discovery uses. A context with more files than this is a
mistake (someone forgot a .dockerignore), and hashing all of them would make
every run pay for it."""

EXCLUDE_DIRS = frozenset(
    {".git", ".yeet", "node_modules", "__pycache__", ".venv", "venv", "target", "dist", "build"}
)


def build_tag(dockerfile: Path, context: Path | None = None) -> str:
    """`yeet-local/<repo>:<hash12>`.

    The hash covers the Dockerfile's bytes plus the sorted relative paths and
    sizes of the context. Sorted, because `iterdir()` order differs between
    filesystems and an unsorted hash means the cache never hits on one machine
    — the same silent cross-platform bug as `hashFiles()` (trap #10).

    (Deviation from architecture.md 3.5, which writes the tag as
    `yeet-local/<repo>-<hash>`. That form has no tag component, so Docker reads
    it as `:latest` and every build overwrites the last one, which defeats the
    cache the paragraph is about. Same hash input, valid tag.)
    """
    root = context if context is not None else dockerfile.parent
    digest = hashlib.sha256()
    digest.update(dockerfile.read_bytes())
    for line in _context_manifest(root):
        digest.update(line.encode("utf-8"))
    return f"{TAG_PREFIX}/{project_slug(root)}:{digest.hexdigest()[:HASH_LENGTH]}"


def project_slug(root: Path) -> str:
    """`<dirname>-<hash8>` — one stable, path-unique name for one project.

    The directory name alone is not enough and the difference is not academic:
    `~/work/api` and `~/oss/api` would share an image repository, so
    `yeet prune` in one checkout would delete the other's cached image, and two
    concurrent runs would fight over the same container names. Hashing the
    absolute path separates them while keeping the readable part readable.

    Shared with `docker_backend`, which names containers and labels them with
    this, so an image and the containers built from it agree on what project
    they belong to.
    """
    name = root.resolve().name.lower()
    safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in name)
    stem = safe.strip("-.") or "project"
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}"


def _context_manifest(root: Path) -> list[str]:
    """`<relative path>:<size>` per file, sorted. Cheap and good enough.

    Sizes rather than content hashes: reading every byte of a build context on
    every run would cost more than the build we are trying to skip, and a
    same-size edit that changes behaviour will be caught by the Dockerfile hash
    in almost every real case.
    """
    entries: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append(f"{path.relative_to(root).as_posix()}:{size}")
            if len(entries) >= MAX_CONTEXT_FILES:
                return sorted(entries)
    return sorted(entries)


def image_exists(client: Any, reference: str) -> bool:
    """Does this tag exist locally? Any failure means "no" and we rebuild."""
    try:
        client.images.get(reference)
    except Exception:  # noqa: BLE001 - docker raises ImageNotFound and APIError
        return False
    return True


def ensure_built(client: Any, spec: ImageSpec) -> str:
    """Build `spec` if its tag is not already present. Returns the tag.

    Idempotent by construction: the tag *is* the content hash, so a second run
    of an unchanged Dockerfile finds the image and returns immediately.
    """
    if spec.dockerfile is None:
        raise ValueError("ensure_built requires a BUILD ImageSpec")
    context = spec.context or spec.dockerfile.parent
    tag = spec.reference or build_tag(spec.dockerfile, context)
    dockerfile = spec.dockerfile

    def build() -> None:
        client.images.build(
            path=str(context),
            dockerfile=str(dockerfile.relative_to(context))
            if dockerfile.is_relative_to(context)
            else str(dockerfile),
            tag=tag,
            rm=True,
            pull=False,
        )

    return _prepare_once(client, tag, build)


def _prepare_once(
    client: Any,
    reference: str,
    prepare: Callable[[], None],
    notify: Callable[[str], None] | None = None,
) -> str:
    """Check, prepare under the reference's lock, check again.

    The second check is the point: by the time this thread holds the lock,
    another one may have just finished building the very same tag. Re-checking
    inside the lock turns a wave of identical jobs into one build and N cheap
    lookups.

    `notify` is called INSIDE the lock and only when this thread is the one
    doing the work, so "pulling python:3.12" appears once in the log rather
    than once per job. Announcing before the lock would restore the very
    confusion the lock removes: five legs each claiming to pull the image that
    is in fact pulled once.
    """
    if image_exists(client, reference):
        return reference
    with _prep_lock(reference):
        if image_exists(client, reference):
            return reference
        if notify is not None:
            notify(reference)
        try:
            prepare()
        except Exception as exc:  # noqa: BLE001 - docker raises a dozen types
            raise _translate(reference, exc) from exc
    return reference


#: What the daemon says -> what it means. Matched on the message because the
#: SDK collapses nearly everything into `APIError`, so the class is useless and
#: the text is not.
_PULL_CAUSES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        (
            "no such host",
            "temporary failure in name resolution",
            "dial tcp",
            "network is unreachable",
            "i/o timeout",
            "connection timed out",
        ),
        "cannot reach the registry",
        "check your network, or run the job with `cooked_on: local` to skip containers entirely",
    ),
    (
        ("not found", "manifest unknown", "repository does not exist", "404"),
        "no such image",
        "check the spelling and the tag — `python:3.12`, not `python:3.12.0.1`",
    ),
    (
        ("unauthorized", "authentication required", "denied", "403", "401"),
        "the registry refused access",
        "run `docker login` for that registry, or use a public image",
    ),
    (
        ("toomanyrequests", "rate limit", "429"),
        "the registry is rate-limiting this machine",
        "wait, run `docker login` (authenticated pulls have a higher limit), or use a local image",
    ),
    (
        (
            "no matching manifest",
            "does not match the detected host platform",
            "no such image: ",
            "platform",
        ),
        "that image has no build for this machine's architecture",
        "on Apple Silicon try an image with an arm64 build, or add `platform: linux/amd64` "
        "to the job's container and expect it to run under emulation",
    ),
    (
        ("no space left on device",),
        "the disk is full",
        "`docker system prune` frees the images and layers Docker is holding",
    ),
)


def _translate(reference: str, exc: BaseException) -> Exception:
    """A docker exception -> something a person can act on.

    The raw form is `ImageNotFound: 404 Client Error for
    http+docker://localhost/v1.55/images/create?tag=v9&fromImage=x` — which
    contains the answer and buries it behind an API version and a URL-encoded
    query. `detail` keeps the original, because this translation is a guess
    made from a string and a wrong guess must not cost the user the evidence.
    """
    if daemon_is_gone(exc):
        from yeet.executor.backend import DockerUnavailable

        return DockerUnavailable(f"the Docker daemon went away while preparing `{reference}`")

    text = " ".join(str(exc).split())
    lowered = text.lower()
    for markers, message, hint in _PULL_CAUSES:
        if any(marker in lowered for marker in markers):
            return DockerFailure("YEET-E320", f"`{reference}`: {message}", hint=hint, detail=text)
    return DockerFailure("YEET-E320", f"could not prepare the image `{reference}`", detail=text)


def ensure_pulled(client: Any, reference: str, notify: Callable[[str], None] | None = None) -> str:
    """Pull `reference` unless it is already local. One pull per wave, not N."""
    return _prepare_once(client, reference, lambda: client.images.pull(reference), notify)


def find_base_dockerfile(start: Path | None = None) -> Path | None:
    """Locate `Dockerfile.base`.

    Order: an explicit `$YEET_BASE_DOCKERFILE`, then upwards from `start` (a
    dev checkout), then the copy inside the package. Returns None only when
    even that is missing, and the caller turns it into a message naming the
    exact command to run.

    The packaged copy is LAST so a checkout's edited Dockerfile still wins —
    but it exists, which the `__file__`-relative lookup here did not: it
    counted `..` up to the repo root and landed beside site-packages, so every
    installed user got "run `make image`" for a project they never cloned.
    """
    override = os.environ.get(BASE_DOCKERFILE_ENV)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None

    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / BASE_DOCKERFILE
        if candidate.is_file():
            return candidate
    return packaged_path(BASE_DOCKERFILE)


def ensure_base_image(client: Any, *, start: Path | None = None) -> str:
    """Make sure `yeet/ubuntu:22.04` exists, building it once if it does not.

    Deliberately no fallback to plain `ubuntu:22.04`: that image has no git,
    curl or node, so the fallback would "work" and then fail three steps later
    with a confusing error. Trap #3 exists precisely because runners do this.
    """
    if image_exists(client, BASE_IMAGE):
        return BASE_IMAGE
    dockerfile = find_base_dockerfile(start)
    if dockerfile is None:
        raise FileNotFoundError(
            f"{BASE_IMAGE} is not built and {BASE_DOCKERFILE} could not be found. "
            f"Run `make image` from the project, or set ${BASE_DOCKERFILE_ENV}."
        )

    def build() -> None:
        client.images.build(
            path=str(dockerfile.parent),
            dockerfile=dockerfile.name,
            tag=BASE_IMAGE,
            rm=True,
            pull=True,
        )

    # The worst case for the missing lock: the base image takes ~8s to build
    # and EVERY `ubuntu-latest` job in the first wave wants it at once.
    return _prepare_once(client, BASE_IMAGE, build)


def prune(client: Any, root: Path | None = None) -> list[str]:
    """Remove images this tool built. Returns what went.

    Zombie build-cache growth is real (trap #12): every edit to a Dockerfile
    mints a new tag and the old one is never referenced again.

    `root` scopes the removal to ONE project. Without it this removed every
    `yeet-local/*` image on the machine, which is the wrong default the moment
    a second checkout exists: pruning the project you are in should not delete
    the image a colleague's run — or your own other terminal — is about to use.
    Pass None to sweep everything deliberately.
    """
    prefix = f"{TAG_PREFIX}/{project_slug(root)}:" if root is not None else f"{TAG_PREFIX}/"
    removed: list[str] = []
    try:
        images = client.images.list()
    except Exception:  # noqa: BLE001 - nothing to prune if we cannot list
        return removed
    for image in images:
        for tag in list(getattr(image, "tags", []) or []):
            if str(tag).startswith(prefix):
                try:
                    client.images.remove(tag, force=False)
                except Exception:  # noqa: BLE001 - in use by a container; skip it
                    continue
                removed.append(str(tag))
    return removed
