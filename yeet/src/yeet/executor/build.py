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
from pathlib import Path
from typing import Any

from yeet.executor.images import BASE_IMAGE, ImageSpec

TAG_PREFIX = "yeet-local"
BASE_DOCKERFILE = "Dockerfile.base"
BASE_DOCKERFILE_ENV = "YEET_BASE_DOCKERFILE"

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
    return f"{TAG_PREFIX}/{_repo_slug(root)}:{digest.hexdigest()[:HASH_LENGTH]}"


def _repo_slug(root: Path) -> str:
    name = root.resolve().name.lower()
    safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in name)
    return safe.strip("-.") or "project"


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
    if image_exists(client, tag):
        return tag
    client.images.build(
        path=str(context),
        dockerfile=str(spec.dockerfile.relative_to(context))
        if spec.dockerfile.is_relative_to(context)
        else str(spec.dockerfile),
        tag=tag,
        rm=True,
        pull=False,
    )
    return tag


def find_base_dockerfile(start: Path | None = None) -> Path | None:
    """Locate `Dockerfile.base`.

    Order: an explicit `$YEET_BASE_DOCKERFILE`, then the installed package's
    project root (a dev checkout), then upwards from `start`. Returns None when
    there is nothing to build, and the caller turns that into a message telling
    the user the exact command to run.
    """
    override = os.environ.get(BASE_DOCKERFILE_ENV)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None

    # src/yeet/executor/build.py -> src/yeet -> src -> <project root>
    packaged = Path(__file__).resolve().parents[3] / BASE_DOCKERFILE
    if packaged.is_file():
        return packaged

    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / BASE_DOCKERFILE
        if candidate.is_file():
            return candidate
    return None


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
    client.images.build(
        path=str(dockerfile.parent),
        dockerfile=dockerfile.name,
        tag=BASE_IMAGE,
        rm=True,
        pull=True,
    )
    return BASE_IMAGE


def prune(client: Any) -> list[str]:
    """Remove every image this tool built. Returns what went.

    Zombie build-cache growth is real (trap #12): every edit to a Dockerfile
    mints a new tag and the old one is never referenced again.
    """
    removed: list[str] = []
    try:
        images = client.images.list()
    except Exception:  # noqa: BLE001 - nothing to prune if we cannot list
        return removed
    for image in images:
        for tag in list(getattr(image, "tags", []) or []):
            if tag.startswith(f"{TAG_PREFIX}/"):
                try:
                    client.images.remove(tag, force=False)
                except Exception:  # noqa: BLE001 - in use by a container; skip it
                    continue
                removed.append(str(tag))
    return removed
