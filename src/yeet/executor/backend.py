"""Protocol both backends implement. Keeps Docker out of everyone else's imports.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from yeet.core.builtins import BuiltinRunner
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
    builtins: BuiltinRunner | None = None
    """Runs `actions/cache` / `upload-artifact`. Same indirection as `sink` and
    for the same reason: the implementation is in `storage`, which this tier may
    not import. `cli/cmd_run` supplies it."""
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


class DockerFailure(Exception):
    """The daemon is fine; it refused to do the thing. Reads like a Diagnostic.

    Everything the user sees about a failed pull, build, container start or
    exec comes through here, because the alternative is what they got before:
    `ImageNotFound: 404 Client Error for http+docker://localhost/v1.55/images/
    create?tag=v9&fromImage=...`. That string contains the answer and buries it
    behind an API version and a URL-encoded query.

    Carries the raw daemon text in `detail` rather than discarding it — the
    translation is a best guess made from a string, and when the guess is wrong
    the user still needs the original to search for.
    """

    def __init__(self, code: str, message: str, *, hint: str = "", detail: str = "") -> None:
        super().__init__("\n".join(self.lines(code, message, hint=hint, detail=detail)))
        self.code = code
        self.message = message
        self.hint = hint
        self.detail = detail

    @staticmethod
    def lines(code: str, message: str, *, hint: str, detail: str) -> list[str]:
        out = [f"{code}: {message}"]
        if hint:
            out.append(f"  fix: {hint}")
        if detail and detail not in message:
            out.append(f"  docker said: {detail}")
        return out

    @property
    def report(self) -> list[str]:
        """One log line each. A sink renders lines, not paragraphs."""
        return self.lines(self.code, self.message, hint=self.hint, detail=self.detail)


DAEMON_GONE_MARKERS = (
    "connection aborted",
    "connection refused",
    "connection reset",
    "cannot connect to the docker daemon",
    "error while fetching server api version",
    "is the docker daemon running",
    "broken pipe",
    "connectionerror",
    "remote end closed connection",
    "not supported by the daemon",
)
"""Substrings that mean "the daemon went away", not "the daemon said no".

Matched on text rather than on `docker.errors.*` classes because the SDK
collapses almost everything into `APIError`/`DockerException`: the class tells
us nothing useful and the message tells us everything. It also keeps this
module importable — and this logic testable — without the SDK installed.
"""


def daemon_is_gone(exc: BaseException) -> bool:
    """Did this exception mean the daemon died, rather than said no?

    Walks `__cause__`/`__context__` because requests wraps the socket error and
    docker-py wraps that again: the words that matter are three levels down.
    """
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < 5:
        text = f"{type(current).__name__}: {current}".lower()
        if any(marker in text for marker in DAEMON_GONE_MARKERS):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


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
        raise DockerUnavailable(f"cannot reach the Docker daemon: {_one_line(exc)}") from exc
    return client


def _one_line(exc: BaseException) -> str:
    """The exception's message with the newlines taken out.

    Docker Desktop's "starting up" error is three lines of shell suggestion;
    inside a log sink that is three events, one of which is the actual reason.
    """
    return " ".join(str(exc).split())
