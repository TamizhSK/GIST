"""Protocol both backends implement. Keeps Docker out of everyone else's imports.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from yeet.core.events import LogSink
from yeet.core.masking import Masker
from yeet.core.result import JobResult
from yeet.executor.platform_ import docker_host_hint
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import JobInstance


@dataclass
class JobContext:
    """Everything a job needs that is not in the Job itself.

    `secrets` is a Masker, not a dict: the executor's job is to redact values,
    not to know them. And `sink` is a Protocol rather than a storage object, so
    the executor never imports `storage` (they are independent siblings at
    tier 5 — lint-imports rejects that edge). Both indirections exist for the
    tier rule and both make this class trivial to fake in a test.
    """

    workspace: Path
    env: dict[str, str] = field(default_factory=dict)
    secrets: Masker = field(default_factory=Masker)
    sink: LogSink | None = None
    needs: dict[str, JobResult] = field(default_factory=dict)
    event: str = "push"
    contexts: Contexts | None = None
    """Dev B's evaluation contexts, for `${{ }}` in `run:` and step-level `if:`.

    Added after C1b, with a default, so no existing caller changes. None means
    "no expression engine available" and `interpolate` degrades visibly rather
    than silently — see executor/interpolate.py."""
    run_id: str = ""
    """Empty means "make one". The runner sets it so every job of a run shares
    a scratch directory and a log directory."""


@runtime_checkable
class Backend(Protocol):
    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult: ...


class DockerUnavailable(Exception):
    """No reachable daemon. The CLI turns this into exit code 3.

    Exit 3 is distinct from 1 on purpose: "your workflow failed" and "this
    machine cannot run containers" are different facts, and a trainer piping
    our exit code into something needs to tell them apart.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"{detail}\n{docker_host_hint()}")
        self.detail = detail
        self.hint = docker_host_hint()


def get_docker_client() -> Any:
    """`docker.from_env()`, with an error a human can act on.

    `import docker` happens inside the function, not at module scope. Importing
    this module must stay cheap and daemon-free: `local_backend` needs
    `JobContext` from here and has nothing to do with Docker, and `yeet check`
    should never pay for the SDK at all.

    `from_env()` already handles the unix socket and the Windows named pipe via
    DOCKER_HOST, so there is no platform branch here — only in the message.
    """
    try:
        import docker
    except ImportError as exc:  # pragma: no cover - docker is a hard dependency
        raise DockerUnavailable(f"the docker SDK is not importable: {exc}") from exc

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001 - DockerException et al
        raise DockerUnavailable(f"cannot reach the Docker daemon: {exc}") from exc
    return client
