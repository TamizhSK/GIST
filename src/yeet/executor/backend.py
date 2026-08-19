"""Protocol both backends implement. Keeps Docker out of everyone else's imports.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import os
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
    """THE directory the job's steps run in, on the host side of the mount.

    Equal to the project root for a normal run — the working tree is bind-mounted
    and you are testing what you are editing. Under `yeet run --clean` it is this
    job's own empty directory, and `actions/checkout` fills it exactly as on
    GitHub. Per JOB, not per run: two legs of a matrix must not share a checkout.

    A backend must read this and never substitute its own root. It went four
    sessions with no reader at all, which is why `--clean` created an empty
    directory and then ran against the working tree anyway."""
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
    offline: bool = False
    """`yeet run --offline` — a remote `uses:` may be served from the action
    cache but must not fetch."""


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


CANDIDATE_TIMEOUT_S = 5
"""Per fallback endpoint. Short on purpose: this only runs after the configured
one has already failed, and the user is waiting. Several dead sockets at
docker-py's 60-second default would be a minute of silence before an error."""


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
    # Windows. A daemon that dies MID-RUN — Docker Desktop restarting for an
    # update is the everyday case — leaves a broken named pipe, and none of the
    # POSIX phrasings above appear. Pipe-specific rather than the generic
    # "system cannot find the file specified", which is a Win32 string common
    # enough to match errors that have nothing to do with the daemon.
    "//./pipe/",
    "%2f%2f.%2fpipe%2f",
    "pipe/docker_engine",
    "pipe/dockerdesktoplinuxengine",
    "the docker daemon is not running",
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
    """`docker.from_env()`, then every endpoint this machine might be using.

    `import docker` happens inside the function, not at module scope. Importing
    this module must stay cheap and daemon-free: `local_backend` needs
    `JobContext` from here and has nothing to do with Docker, and `yeet check`
    should never pay for the SDK at all.

    `from_env()` reads `$DOCKER_HOST` AND NOTHING ELSE, which is the whole
    problem: the `docker` CLI reads `docker context`, and Colima, Rancher
    Desktop, Podman, Lima and rootless dockerd all set up a context without
    ever exporting `DOCKER_HOST`. On every one of those machines `docker ps`
    works in the terminal while this function used to report no daemon at all.
    `platform_.docker_host_candidates()` is the list the CLI would have
    consulted, and it covers macOS, Linux, WSL and Windows named pipes.

    The endpoint that answers is written back to `$DOCKER_HOST` so that the
    parts of yeet that shell out to the `docker` BINARY — `actions/fetch.py`'s
    git container — end up talking to the same daemon this client is on. Two
    halves of one run must not disagree about which machine they are on.

    The error, when everything fails, is the one from `from_env()`: it is the
    endpoint the user configured (or the default), so it is the failure they
    can actually act on. Reporting the last candidate's would name a socket
    they have never heard of.
    """
    try:
        import docker
    except ImportError as exc:  # pragma: no cover - docker is a hard dependency
        raise DockerUnavailable(f"the docker SDK is not importable: {exc}") from exc

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001 - DockerException et al
        primary = exc
    else:
        return client

    client = _try_candidates(docker)
    if client is not None:
        return client
    raise DockerUnavailable(_no_daemon_reason(primary)) from primary


def _try_candidates(docker: Any) -> Any | None:
    """Ping each known endpoint in turn; the first that answers wins.

    Deliberately silent about the ones that do not answer. A machine with
    Docker Desktop installed and Colima not running is completely normal, and
    printing a line per miss would turn one clean failure into six confusing
    ones.
    """
    from yeet.executor.platform_ import docker_host_candidates

    for host in docker_host_candidates():
        try:
            client = docker.DockerClient(base_url=host, timeout=CANDIDATE_TIMEOUT_S)
            client.ping()
        except Exception:  # noqa: BLE001 - a candidate that is not there is the normal case
            continue
        os.environ["DOCKER_HOST"] = host
        return client
    return None


def _no_daemon_reason(exc: BaseException) -> str:
    """Why the daemon is unreachable, in words rather than in a tuple repr.

    docker-py reports a missing socket as `Error while fetching server API
    version: ('Connection aborted.', FileNotFoundError(2, 'No such file or
    directory'))`. Every word of that is about our HTTP client and none of it
    is about the user's machine, which is simply not running Docker.

    WINDOWS SAYS IT COMPLETELY DIFFERENTLY, and used to fall through to the
    catch-all. There the daemon is a named pipe, so a stopped Docker Desktop
    reads `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the
    file specified` — no "connection refused", no "no such file or directory".
    The most common Docker failure on the most common desktop OS was the one
    case with no translation, and the user got the raw pipe path instead of
    "Docker Desktop is not running".
    """
    text = _one_line(exc).lower()
    if "permission denied" in text or "access is denied" in text:
        return "the Docker socket exists but this user cannot open it"
    if "timed out" in text or "timeout" in text:
        return "the Docker daemon did not answer in time (still starting up?)"
    if any(marker in text for marker in _NOT_LISTENING_MARKERS):
        return "no Docker daemon is listening"
    return f"cannot reach the Docker daemon: {_one_line(exc)}"


_NOT_LISTENING_MARKERS = (
    "no such file or directory",
    "connection refused",
    # Windows named pipes. The first is what a stopped Docker Desktop returns
    # (ERROR_FILE_NOT_FOUND on the pipe), the second what a starting one does
    # while the pipe exists but nothing is serving it yet.
    "the system cannot find the file specified",
    "the system cannot find the path specified",
    "cannot find the file",
    "all pipe instances are busy",
    "//./pipe/",
    r"\\.\pipe",
)
"""Every way the three platforms spell "there is nothing on the other end".

Checked AFTER permission and timeout because the Windows phrasings are broad:
"the system cannot find the file specified" is a generic Win32 error string and
a permission problem that happens to mention it must still read as one."""


def _one_line(exc: BaseException) -> str:
    """The exception's message with the newlines taken out.

    Docker Desktop's "starting up" error is three lines of shell suggestion;
    inside a log sink that is three events, one of which is the actual reason.
    """
    return " ".join(str(exc).split())
