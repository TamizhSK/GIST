"""ONE container per job, exec per step. Never docker-run per step.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import atexit
import contextlib
import signal
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import FrameType
from typing import Any

from yeet.core.events import META, STDERR, STDOUT, LogEvent
from yeet.core.project import Project
from yeet.core.result import JobResult, Status, StepResult
from yeet.executor import build as build_mod
from yeet.executor import env as env_mod
from yeet.executor.backend import JobContext, get_docker_client
from yeet.executor.images import ImageKind, ImageResolutionError, ImageSpec, resolve_image
from yeet.executor.paths import CONTAINER_WORKSPACE, to_container_path, to_workspace_path
from yeet.executor.platform_ import docker_user
from yeet.executor.steps import (
    Chunk,
    StepLoopConfig,
    StepRequest,
    build_job_result,
    label,
    run_steps,
)
from yeet.executor.workspace import RunLayout, create, slug
from yeet.planner.plan import JobInstance

KEEPALIVE_CMD = ["tail", "-f", "/dev/null"]

CONTAINER_PREFIX = "yeet"
STOP_TIMEOUT_S = 5

_LIVE: dict[str, Any] = {}
_LIVE_LOCK = threading.Lock()
_HANDLERS_INSTALLED = False


def _track(container: Any) -> None:
    with _LIVE_LOCK:
        _LIVE[container.id] = container


def _untrack(container: Any) -> None:
    with _LIVE_LOCK:
        _LIVE.pop(container.id, None)


def reap_all() -> None:
    """Stop and remove every container we started. Idempotent, never raises.

    Risk #9: a Ctrl-C during a long `npm ci` must not leave a container holding
    the workspace open. `finally` covers the normal path; this covers the two
    that skip `finally` entirely — a signal and interpreter shutdown.
    """
    with _LIVE_LOCK:
        containers = list(_LIVE.values())
        _LIVE.clear()
    for container in containers:
        _force_remove(container)


def _force_remove(container: Any) -> None:
    # Suppressed on purpose: this runs from a signal handler and from atexit,
    # where the daemon may already be gone. A cleanup that raises would replace
    # the user's real error with ours.
    with contextlib.suppress(Exception):
        container.stop(timeout=STOP_TIMEOUT_S)
    with contextlib.suppress(Exception):
        container.remove(force=True)


def install_cleanup_handlers() -> None:
    """atexit + SIGINT/SIGTERM. Safe to call more than once.

    `signal.signal` raises off the main thread, and the runner calls backends
    from a pool — so the guard is not defensive noise, it is the difference
    between working and a ValueError on every job.
    """
    global _HANDLERS_INSTALLED
    if _HANDLERS_INSTALLED:
        return
    atexit.register(reap_all)
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(sig)

            def handler(signum: int, frame: FrameType | None, _previous: Any = previous) -> None:
                reap_all()
                if callable(_previous):
                    _previous(signum, frame)
                else:
                    raise KeyboardInterrupt

            signal.signal(sig, handler)
    _HANDLERS_INSTALLED = True


class DockerExec:
    """A `steps.StepExec` that runs one step inside an already-live container.

    THE TRAP. `container.exec_run(stream=True)` returns `exit_code=None` —
    streaming and the status code are mutually exclusive in the high-level API,
    so a naive implementation reads `None`, compares it to 0, and reports every
    step as passing no matter what happened. Hence the low-level three-step
    dance: exec_create -> exec_start(stream, demux) -> exec_inspect for the
    real code.
    """

    def __init__(self, client: Any, container: Any) -> None:
        self._client = client
        self._container = container

    def exec_step(self, request: StepRequest) -> tuple[int, Iterable[Chunk]]:
        api = self._client.api
        workdir = (
            f"{CONTAINER_WORKSPACE}/{request.workdir}" if request.workdir else CONTAINER_WORKSPACE
        )
        handle = api.exec_create(
            self._container.id,
            cmd=request.argv,
            environment=request.env,
            workdir=workdir,
            stdout=True,
            stderr=True,
        )
        exec_id = handle["Id"]
        stream = api.exec_start(exec_id, stream=True, demux=True)
        chunks = list(_demux(stream, deadline=_deadline(request.timeout_s)))
        exit_code = api.exec_inspect(exec_id).get("ExitCode")
        return (exit_code if isinstance(exit_code, int) else 1), chunks


def _deadline(timeout_s: float | None) -> float | None:
    return time.monotonic() + timeout_s if timeout_s else None


def _demux(
    stream: Iterable[tuple[bytes | None, bytes | None]], *, deadline: float | None
) -> Iterator[Chunk]:
    for out, err in stream:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("step exceeded its timeout")
        if out:
            yield STDOUT, out
        if err:
            yield STDERR, err


class DockerBackend:
    """Implements `backend.Backend`.

    The core insight: create ONE container per job and `exec_run` each step
    inside it. A `docker run` per step loses every bit of state between steps —
    cd, exported vars, installed packages — which is the bug that makes naive
    implementations mysteriously fail on real workflows.

    Cleanup goes in a `finally`, plus atexit and SIGINT/SIGTERM handlers.
    Ctrl-C must not leave containers running.
    """

    def __init__(
        self,
        root: Path,
        *,
        project: Project | None = None,
        client: Any = None,
        layout: RunLayout | None = None,
    ) -> None:
        self.root = root
        self.project = project or Project(root=root)
        self._client = client
        self._layout = layout
        install_cleanup_handlers()

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = get_docker_client()
        return self._client

    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult:
        started = time.monotonic()
        layout = self._layout or create(self.root, ctx.run_id or None)
        job_layout = layout.job(inst.key)

        base = env_mod.container_base_env(run_id=layout.run_id, job_key=inst.key, event=ctx.event)
        base.update(ctx.env)

        config = StepLoopConfig(
            job=inst.job,
            job_key=inst.key,
            layout=job_layout,
            root=self.root,
            base_env=base,
            masker=ctx.secrets,
            to_step_path=lambda path: to_workspace_path(path, self.root),
            sink=ctx.sink,
            contexts=ctx.contexts,
            in_container=True,
        )

        try:
            image = self._ensure_image(inst, config)
        except ImageResolutionError as exc:
            _note(config, str(exc.diagnostic))
            return JobResult(
                job_key=inst.key,
                matrix_leg=dict(inst.leg),
                status=Status.FAILURE,
                steps=[
                    StepResult(step_name=label(step), status=Status.SKIPPED)
                    for step in inst.job.steps
                ],
                duration_s=time.monotonic() - started,
            )

        container = self._create(image, inst, base)
        try:
            container.start()
            results = run_steps(config, DockerExec(self.client, container))
        finally:
            _untrack(container)
            _force_remove(container)

        return build_job_result(config, inst, results, started)

    def _ensure_image(self, inst: JobInstance, config: StepLoopConfig) -> str:
        spec: ImageSpec = resolve_image(inst.job, self.project)
        if spec.note:
            _note(config, spec.note)

        if spec.kind is ImageKind.BASE:
            _note(config, f"base image: {spec.reference}")
            return str(build_mod.ensure_base_image(self.client, start=self.root))

        if spec.kind is ImageKind.BUILD:
            tag = build_mod.build_tag(spec.dockerfile, spec.context) if spec.dockerfile else ""
            if build_mod.image_exists(self.client, tag):
                _note(config, f"cached image {tag} — skipping the build")
                return tag
            _note(config, f"building {tag}")
            return str(build_mod.ensure_built(self.client, spec))

        if not build_mod.image_exists(self.client, spec.reference):
            _note(config, f"pulling {spec.reference}")
            self.client.images.pull(spec.reference)
        return spec.reference

    def _create(self, image: str, inst: JobInstance, base: dict[str, str]) -> Any:
        source = to_container_path(self.root.resolve())
        container = self.client.containers.create(
            image=image,
            command=KEEPALIVE_CMD,
            name=f"{CONTAINER_PREFIX}-{slug(inst.key)}-{int(time.time() * 1000) % 1_000_000}",
            working_dir=CONTAINER_WORKSPACE,
            volumes={source: {"bind": CONTAINER_WORKSPACE, "mode": "rw"}},
            environment=base,
            # None on Docker Desktop. Passing a host uid there breaks the
            # container instead of fixing ownership — risk #6.
            user=docker_user(),
            network_mode="bridge",
            auto_remove=False,
            tty=False,
        )
        _track(container)
        return container


def _note(config: StepLoopConfig, text: str) -> None:
    """A runner-level line, outside any step. Masked like everything else."""
    if config.sink is None:
        return
    config.sink.emit(
        LogEvent.now(job=config.job_key, step="", stream=META, text=config.masker.mask(text))
    )
