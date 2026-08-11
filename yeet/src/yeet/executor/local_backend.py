"""runs-on: local — host shell. bash, or pwsh on Windows.

The escape hatch for `cooked_on: local`, and — just as important — the backend
the fast test suite uses. Everything in `steps.py` (masking, `::` directives,
state-file read-back, `continue-on-error`, timeouts) is exercised here without
a daemon, so `pytest -m "not docker"` is real evidence rather than a mock
agreeing with itself.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import IO

from yeet.core.events import STDERR, STDOUT
from yeet.core.result import JobResult
from yeet.executor import env as env_mod
from yeet.executor.backend import JobContext
from yeet.executor.steps import (
    Chunk,
    StepLoopConfig,
    StepRequest,
    build_job_result,
    run_steps,
)
from yeet.executor.workspace import RunLayout, create
from yeet.planner.plan import JobInstance

READ_SIZE = 4096


class LocalExec:
    """A `steps.StepExec` backed by `subprocess.Popen`.

    Two reader threads rather than `communicate()`: the log format records
    which stream each line came from, so stdout and stderr have to stay apart,
    and they have to arrive as they are produced. `communicate()` gives
    neither, and reading one pipe then the other deadlocks the moment a step
    writes more than a pipe buffer to stderr.
    """

    def __init__(self, cwd: Path) -> None:
        self._cwd = cwd

    def exec_step(self, request: StepRequest) -> tuple[int, Iterable[Chunk]]:
        cwd = self._cwd / request.workdir if request.workdir else self._cwd
        process = subprocess.Popen(
            request.argv,
            cwd=str(cwd),
            env=request.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        chunks: list[Chunk] = []
        lock = threading.Lock()

        def drain(pipe: IO[bytes] | None, name: str) -> None:
            if pipe is None:  # pragma: no cover - PIPE is always requested
                return
            while True:
                data = pipe.read(READ_SIZE)
                if not data:
                    break
                with lock:
                    chunks.append((name, data))

        readers = [
            threading.Thread(target=drain, args=(process.stdout, STDOUT), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, STDERR), daemon=True),
        ]
        for reader in readers:
            reader.start()

        try:
            exit_code = process.wait(timeout=request.timeout_s)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=1.0)
            raise TimeoutError(str(exc)) from exc

        for reader in readers:
            reader.join(timeout=5.0)
        return exit_code, chunks


class LocalBackend:
    """Implements `backend.Backend` with no container at all."""

    def __init__(self, root: Path, *, layout: RunLayout | None = None) -> None:
        self.root = root
        self._layout = layout

    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult:
        started = time.monotonic()
        layout = self._layout or create(self.root, ctx.run_id or None)
        job_layout = layout.job(inst.key)

        # The host environment is the starting point, unlike the container
        # backend. Two reasons: `cooked_on: local` means "use my machine", so
        # inheriting HOME, SHELL and the user's toolchain is the intent; and
        # `Popen(env=...)` resolves argv[0] through the PATH *in that env*, so
        # dropping it means `bash` itself cannot be found.
        base = dict(os.environ)
        base.update(
            env_mod.base_env(
                workspace=str(self.root),
                run_id=layout.run_id,
                job_key=inst.key,
                event=ctx.event,
                runner_temp=str(job_layout.dir),
            )
        )
        base.update(ctx.env)

        config = StepLoopConfig(
            job=inst.job,
            job_key=inst.key,
            layout=job_layout,
            root=self.root,
            base_env=base,
            masker=ctx.secrets,
            to_step_path=str,
            sink=ctx.sink,
            contexts=ctx.contexts,
            in_container=False,
        )

        results = run_steps(config, LocalExec(self.root))
        return build_job_result(config, inst, results, started)
