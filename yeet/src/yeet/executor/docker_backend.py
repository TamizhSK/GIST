"""ONE container per job, exec per step. Never docker-run per step.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from yeet.core.result import JobResult
from yeet.executor.backend import JobContext
from yeet.planner.plan import JobInstance

KEEPALIVE_CMD = ["tail", "-f", "/dev/null"]


class DockerBackend:
    """Implements `backend.Backend`.

    The core insight: create ONE container per job and `exec_run` each step
    inside it. A `docker run` per step loses every bit of state between steps —
    cd, exported vars, installed packages — which is the bug that makes naive
    implementations mysteriously fail on real workflows.

    Cleanup goes in a `finally`, plus atexit and SIGINT/SIGTERM handlers.
    Ctrl-C must not leave containers running.
    """

    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult:
        raise NotImplementedError
