"""Wave scheduling, needs propagation and skip semantics — with a fake backend.

The reason `runner.py` is not inside `cmd_run.py`: this whole file would
otherwise have to go through Typer to reach the logic it tests.
"""

from __future__ import annotations

import threading
import time

from conftest import POS, make_instance, make_job, make_matrix, make_step

from yeet.core.events import ListSink
from yeet.core.ir import Strategy
from yeet.core.result import JobResult, Status
from yeet.executor.backend import JobContext
from yeet.executor.runner import RunOptions, run_plan
from yeet.planner.plan import ExecutionPlan, JobInstance


class FakeBackend:
    """Records what it was handed, and returns whatever you tell it to."""

    def __init__(self, statuses: dict[str, Status] | None = None, delay: float = 0.0) -> None:
        self.statuses = statuses or {}
        self.delay = delay
        self.seen: list[str] = []
        self.contexts: dict[str, JobContext] = {}
        self.concurrent = 0
        self.peak = 0
        self._lock = threading.Lock()

    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult:
        with self._lock:
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
            self.seen.append(inst.key)
            self.contexts[inst.key] = ctx
        if self.delay:
            time.sleep(self.delay)
        with self._lock:
            self.concurrent -= 1
        return JobResult(
            job_key=inst.key,
            matrix_leg=dict(inst.leg),
            status=self.statuses.get(inst.key, Status.SUCCESS),
        )


def options(tmp_path, **kwargs):
    return RunOptions(root=tmp_path, workflow_name="test", **kwargs)


def test_waves_run_in_order(tmp_path):
    build = make_instance(make_job("build", [make_step("x")]))
    deploy = make_instance(make_job("deploy", [make_step("x")], needs=["build"]))
    plan = ExecutionPlan(waves=[[build], [deploy]])
    backend = FakeBackend()

    result = run_plan(plan, backend, options(tmp_path))

    assert backend.seen == ["build", "deploy"]
    assert result.status is Status.SUCCESS
    assert result.exit_code == 0


def test_jobs_in_a_wave_run_in_parallel(tmp_path):
    wave = [make_instance(make_job(f"job{i}", [make_step("x")])) for i in range(4)]
    backend = FakeBackend(delay=0.05)

    run_plan(ExecutionPlan(waves=[wave]), backend, options(tmp_path, max_workers=4))

    assert backend.peak > 1, "a wave is supposed to be parallel"


def test_the_pool_is_bounded(tmp_path):
    wave = [make_instance(make_job(f"job{i}", [make_step("x")])) for i in range(6)]
    backend = FakeBackend(delay=0.05)

    run_plan(ExecutionPlan(waves=[wave]), backend, options(tmp_path, max_workers=2))

    assert backend.peak <= 2


def test_results_propagate_into_the_needs_context(tmp_path):
    build = make_instance(make_job("build", [make_step("x")]))
    deploy = make_instance(make_job("deploy", [make_step("x")], needs=["build"]))

    backend = FakeBackend()
    run_plan(ExecutionPlan(waves=[[build], [deploy]]), backend, options(tmp_path))

    needs = backend.contexts["deploy"].needs
    assert "build" in needs
    assert needs["build"].status is Status.SUCCESS


def test_a_downstream_job_is_skipped_when_its_dependency_flops(tmp_path):
    build = make_instance(make_job("build", [make_step("x")]))
    deploy = make_instance(make_job("deploy", [make_step("x")], needs=["build"]))
    backend = FakeBackend({"build": Status.FAILURE})
    sink = ListSink()

    result = run_plan(
        ExecutionPlan(waves=[[build], [deploy]]), backend, options(tmp_path, sink=sink)
    )

    assert backend.seen == ["build"], "deploy must never have been started"
    statuses = {job.job_key: job.status for job in result.jobs}
    assert statuses == {"build": Status.FAILURE, "deploy": Status.SKIPPED}
    assert "not the vibe" in sink.text()
    assert result.exit_code == 1


def test_always_runs_even_after_a_failure(tmp_path):
    build = make_instance(make_job("build", [make_step("x")]))
    notify = make_instance(
        make_job("notify", [make_step("x")], needs=["build"], if_="${{ always() }}")
    )
    backend = FakeBackend({"build": Status.FAILURE})

    run_plan(ExecutionPlan(waves=[[build], [notify]]), backend, options(tmp_path))

    assert "notify" in backend.seen


def test_failure_marker_also_runs(tmp_path):
    build = make_instance(make_job("build", [make_step("x")]))
    alert = make_instance(make_job("alert", [make_step("x")], needs=["build"], if_="failure()"))
    backend = FakeBackend({"build": Status.FAILURE})

    run_plan(ExecutionPlan(waves=[[build], [alert]]), backend, options(tmp_path))

    assert "alert" in backend.seen


def test_a_skipped_dependency_does_not_block_a_downstream_job(tmp_path):
    """SKIPPED is `ok` — only a real failure stops the chain."""
    build = make_instance(make_job("build", [make_step("x")]))
    deploy = make_instance(make_job("deploy", [make_step("x")], needs=["build"]))
    backend = FakeBackend({"build": Status.SKIPPED})

    run_plan(ExecutionPlan(waves=[[build], [deploy]]), backend, options(tmp_path))

    assert "deploy" in backend.seen


def test_matrix_legs_map_back_to_their_job_for_needs(tmp_path):
    """`needs: [build]` has to match `build (node 20)`, not just `build`."""
    job = make_job("build", [make_step("x")], strategy=make_matrix(node=[18, 20]))
    legs = [
        make_instance(job, key="build (node 18)", leg={"node": 18}),
        make_instance(job, key="build (node 20)", leg={"node": 20}),
    ]
    deploy = make_instance(make_job("deploy", [make_step("x")], needs=["build"]))

    backend = FakeBackend()
    run_plan(ExecutionPlan(waves=[legs, [deploy]]), backend, options(tmp_path))

    assert set(backend.contexts["deploy"].needs) == {"build (node 18)", "build (node 20)"}


def test_fail_fast_cancels_sibling_matrix_legs(tmp_path):
    """fail-fast on: the first failing leg cancels queued siblings of the same job."""
    job = make_job("build", [make_step("x")], strategy=make_matrix(node=[18, 20]))
    fast = make_instance(job, key="build (node 18)", leg={"node": 18})
    slow = make_instance(job, key="build (node 20)", leg={"node": 20})
    backend = FakeBackend({"build (node 18)": Status.FAILURE})
    sink = ListSink()

    result = run_plan(
        ExecutionPlan(waves=[[fast, slow]]), backend, options(tmp_path, sink=sink, max_workers=1)
    )

    assert backend.seen == ["build (node 18)"], "the sibling must never have started"
    statuses = {job.job_key: job.status for job in result.jobs}
    assert statuses == {"build (node 18)": Status.FAILURE, "build (node 20)": Status.SKIPPED}
    assert "cancelled (fail-fast)" in sink.text()
    assert result.exit_code == 1


def test_fail_fast_off_lets_siblings_run(tmp_path):
    job = make_job(
        "build",
        [make_step("x")],
        strategy=Strategy(pos=POS, matrix={"node": [18, 20]}, fail_fast=False),
    )
    fast = make_instance(job, key="build (node 18)", leg={"node": 18})
    slow = make_instance(job, key="build (node 20)", leg={"node": 20})
    backend = FakeBackend({"build (node 18)": Status.FAILURE})

    result = run_plan(
        ExecutionPlan(waves=[[fast, slow]]), backend, options(tmp_path, max_workers=1)
    )

    assert backend.seen == ["build (node 18)", "build (node 20)"]
    statuses = {job.job_key: job.status for job in result.jobs}
    assert statuses == {"build (node 18)": Status.FAILURE, "build (node 20)": Status.SUCCESS}


def test_fail_fast_only_cancels_siblings_of_the_same_job(tmp_path):
    build = make_job("build", [make_step("x")], strategy=make_matrix(node=[18, 20]))
    lint = make_job("lint", [make_step("x")], strategy=make_matrix(node=[18]))
    fast = make_instance(build, key="build (node 18)", leg={"node": 18})
    slow = make_instance(build, key="build (node 20)", leg={"node": 20})
    lint_inst = make_instance(lint, key="lint (node 18)", leg={"node": 18})
    backend = FakeBackend({"build (node 18)": Status.FAILURE})

    result = run_plan(
        ExecutionPlan(waves=[[fast, slow, lint_inst]]), backend, options(tmp_path, max_workers=1)
    )

    statuses = {job.job_key: job.status for job in result.jobs}
    assert statuses == {
        "build (node 18)": Status.FAILURE,
        "build (node 20)": Status.SKIPPED,
        "lint (node 18)": Status.SUCCESS,
    }
    assert backend.seen == ["build (node 18)", "lint (node 18)"]


def test_a_backend_that_raises_becomes_a_failed_job(tmp_path):
    class Exploding:
        def run_job(self, inst, ctx):
            raise RuntimeError("the daemon died")

    inst = make_instance(make_job("build", [make_step("x")]))
    sink = ListSink()

    result = run_plan(ExecutionPlan(waves=[[inst]]), Exploding(), options(tmp_path, sink=sink))

    assert result.status is Status.FAILURE
    assert "the daemon died" in sink.text()


def test_an_empty_plan_is_a_success(tmp_path):
    result = run_plan(ExecutionPlan(waves=[]), FakeBackend(), options(tmp_path))
    assert result.status is Status.SUCCESS
    assert result.exit_code == 0


def test_the_run_id_is_shared_by_every_job(tmp_path):
    wave = [make_instance(make_job(f"job{i}", [make_step("x")])) for i in range(3)]
    backend = FakeBackend()

    result = run_plan(ExecutionPlan(waves=[wave]), backend, options(tmp_path))

    ids = {ctx.run_id for ctx in backend.contexts.values()}
    assert ids == {result.run_id}


def test_worker_count_never_exceeds_the_job_count(tmp_path):
    plan = ExecutionPlan(waves=[[make_instance(make_job("only", [make_step("x")]))]])
    assert options(tmp_path, max_workers=32).workers(plan) == 1
