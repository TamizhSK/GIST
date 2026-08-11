"""runs-on value -> image name. ubuntu-latest -> our base image.

The whole resolution table from architecture.md 3.5 and nothing else: this
module is pure, takes no Docker client and touches no network. `build.py` acts
on what it returns.

E315 NOTE FOR STANDUP. architecture.md documents E315 ("cooked_on can't be
resolved and no Dockerfile was found") as a Layer 3 code, but resolution needs
`Project` *and* this table, and validation is tier 3 while the executor is tier
5 — Layer 3 cannot import this module. So E315 fires here, at run time, before
any container is created. The gate still holds; it just holds one step later
than the doc implies. Moving it would mean moving the table into `core/`, and
`core/` is closed (plan.md 3).

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Job
from yeet.core.project import Project

BASE_IMAGE = "yeet/ubuntu:22.04"
"""Built from Dockerfile.base. NOT plain `ubuntu:22.04` — that image has no
git, no curl and no node, and a workflow using any of them fails with an error
that points nowhere near the real cause (trap #3)."""

UBUNTU_ALIASES = frozenset({"ubuntu-latest", "ubuntu-22.04", "ubuntu-24.04", "ubuntu"})
LOCAL_ALIASES = frozenset({"local", "native", "host"})

DOCKERFILE_NAME = "Dockerfile"


class ImageKind(str, Enum):  # noqa: UP042 - matches the Status/Severity convention
    BASE = "base"
    """Our prebuilt base image."""
    PULL = "pull"
    """A published image:tag — pull it."""
    BUILD = "build"
    """A Dockerfile in the project — build it, tag by content hash."""
    LOCAL = "local"
    """No container at all. `local_backend` runs it in the host shell."""


@dataclass(frozen=True, slots=True)
class ImageSpec:
    kind: ImageKind
    reference: str
    """The image name to run. For BUILD it is filled in by `build.ensure_built`."""
    dockerfile: Path | None = None
    context: Path | None = None
    note: str | None = None
    """A line worth showing the user, e.g. the auto-detect explanation."""

    @property
    def needs_container(self) -> bool:
        return self.kind is not ImageKind.LOCAL


class ImageResolutionError(Exception):
    """Nothing resolved. Carries the E315 Diagnostic the CLI will render."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def resolve_image(job: Job, project: Project) -> ImageSpec:
    """`cooked_on:`/`runs-on:` -> what to run the job in.

    Order matters. An explicit `container_image:` beats `runs-on`, because a
    user who wrote both meant the specific one. `dockerfile:` beats both.
    """
    if job.dockerfile:
        path = _resolve_dockerfile(project.root, job.dockerfile)
        return _build_spec(path, project, note=f"dockerfile: {job.dockerfile}")

    if job.container_image:
        return ImageSpec(kind=ImageKind.PULL, reference=job.container_image)

    runs_on = (job.runs_on or "").strip()

    if not runs_on:
        # The auto-detect requirement: a repo with a Dockerfile and no
        # `cooked_on` should just work.
        if project.dockerfile is not None:
            return _build_spec(
                project.dockerfile,
                project,
                note=f"no cooked_on set -> found ./{project.dockerfile.name} -> building",
            )
        raise ImageResolutionError(_e315(job, "no `cooked_on:` and no Dockerfile in the project"))

    lowered = runs_on.lower()

    if lowered in LOCAL_ALIASES:
        return ImageSpec(kind=ImageKind.LOCAL, reference=lowered)

    if lowered in UBUNTU_ALIASES:
        return ImageSpec(kind=ImageKind.BASE, reference=BASE_IMAGE)

    if runs_on.startswith(("./", "../")) or runs_on.lower().endswith("dockerfile"):
        path = _resolve_dockerfile(project.root, runs_on)
        return _build_spec(path, project, note=f"cooked_on: {runs_on}")

    if _looks_like_image(runs_on):
        return ImageSpec(kind=ImageKind.PULL, reference=runs_on)

    # `windows-latest`, `macos-latest` and friends land here. Say so precisely —
    # "unsupported" is a non-goal we stated, not a bug.
    raise ImageResolutionError(
        _e315(job, f"`cooked_on: {runs_on}` is not a known runner label or image")
    )


def _looks_like_image(value: str) -> bool:
    """`node:20`, `ghcr.io/org/img:sha`, `alpine`. Not `windows-latest`.

    A bare name with no tag and no slash is ambiguous, so we require either a
    tag or a registry path. Guessing wrong here means pulling a random image
    from Docker Hub, which is worse than an error message.
    """
    if "/" in value or ":" in value:
        return True
    return value.isalnum() and value.islower()


def _resolve_dockerfile(root: Path, raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / raw
    return candidate


def _build_spec(dockerfile: Path, project: Project, *, note: str | None) -> ImageSpec:
    if not dockerfile.is_file():
        raise ImageResolutionError(
            Diagnostic(
                code="YEET-E315",
                severity=Severity.ERROR,
                message=f"Dockerfile not found: {dockerfile}",
                file=project.root,
                pos=Position.unknown(),
                help="The path in `cooked_on:` / `dockerfile:` is relative to the project root.",
            )
        )
    return ImageSpec(
        kind=ImageKind.BUILD,
        reference="",  # filled by build.ensure_built
        dockerfile=dockerfile,
        context=dockerfile.parent,
        note=note,
    )


def _e315(job: Job, message: str) -> Diagnostic:
    return Diagnostic(
        code="YEET-E315",
        severity=Severity.ERROR,
        message=f"job `{job.key}`: {message}",
        pos=job.key_pos.get("runs-on", job.pos),
        help=(
            "Use `cooked_on: ubuntu-latest`, an image like `node:20`, "
            "a path to a Dockerfile, or `cooked_on: local` to run on the host."
        ),
    )
