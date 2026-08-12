"""Drive an ExecutionPlan: waves in order, jobs in parallel, results propagated.

WHY THIS FILE EXISTS (plan.md C14 puts this in `cli/cmd_run.py`). A bounded
pool, skip-on-upstream-failure and fail-fast cancellation are about 150 lines
of real logic with real concurrency in them. Inside a Typer command they can
only be tested by invoking the CLI; here they are tested with a five-line fake
backend. plan.md B13 already calls this "Dev C's runner loop" — this is that
loop, and `cmd_run` is left as wiring.

The division of labour with the planner: `planner.plan` decides the shape
(which jobs, which legs, which wave). This module decides what runtime facts
mean — a job whose dependency just flopped cannot be skipped by a planner that
ran before anything executed.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from yeet.core.events import META, LogEvent, LogSink
from yeet.core.masking import Masker
from yeet.core.result import JobResult, RunResult, Status, StepResult
from yeet.executor import env as env_mod
from yeet.executor.backend import Backend, JobContext
from yeet.executor.contexts import for_instance
from yeet.executor.steps import label
from yeet.executor.workspace import RunLayout, create
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import ExecutionPlan, JobInstance

ALWAYS_RUN_MARKERS = ("always()", "failure()", "cancelled()")
"""A job whose `if:` mentions one of these runs even when an upstream flopped —
that is the entire point of writing it. Matched textually here because the
decision has to be made before Dev B's evaluator exists, and it stays correct
afterwards: these four functions are the only ones whose meaning depends on
upstream results, so they are the only ones the runner has to know about."""


@dataclass
class RunOptions:
    """Everything `cmd_run` chooses and the runner obeys."""

    root: Path
    workflow_name: str = ""
    event: str = "push"
    max_workers: int | None = None
    env: dict[str, str] = field(default_factory=dict)
    workflow_env: dict[str, str] = field(default_factory=dict)
    """Workflow-level `env:` / `drip:`. It reached the IR and stopped there —
    `steps._step_env` layers base < exported < job < step and never saw the
    workflow block at all, so a variable declared once at the top of a file was
    invisible to every step under it."""
    masker: Masker = field(default_factory=Masker)
    sink: LogSink | None = None
    contexts: Contexts | None = None
    run_id: str = ""
    layout: RunLayout | None = None

    def workers(self, plan: ExecutionPlan) -> int:
        """Never more threads than there are jobs to put in them."""
        requested = self.max_workers or os.cpu_count() or 1
        return max(1, min(requested, max(1, plan.total_jobs)))


@dataclass
class _State:
    """Results so far, plus which job each instance key belongs to.

    The second map exists because `needs: [build]` names a *job* while results
    are keyed by *instance* (`build (node 20)`). Recovering the job name by
    splitting the string would break the moment someone names a job with a
    bracket in it, so it is recorded instead of parsed.
    """

    results: dict[str, JobResult] = field(default_factory=dict)
    job_of: dict[str, str] = field(default_factory=dict)

    def record(self, inst: JobInstance, result: JobResult) -> None:
        self.results[inst.key] = result
        self.job_of[inst.key] = inst.job.key


def run_plan(plan: ExecutionPlan, backend: Backend, options: RunOptions) -> RunResult:
    """Execute every wave in order. Returns the RunResult the CLI reports on.

    Never raises for a failed job — a flopped build is a result, not an
    exception. Only a broken *tool* raises out of here.
    """
    layout = options.layout or create(options.root, options.run_id or None)
    _align_github_context(options, layout)
    started = time.monotonic()
    state = _State()

    with ThreadPoolExecutor(max_workers=options.workers(plan)) as pool:
        for wave in plan.waves:
            _run_wave(wave, pool, backend, options, layout, state)

    return RunResult(
        run_id=layout.run_id,
        workflow_name=options.workflow_name,
        jobs=list(state.results.values()),
        duration_s=time.monotonic() - started,
    )


def _run_wave(
    wave: list[JobInstance],
    pool: ThreadPoolExecutor,
    backend: Backend,
    options: RunOptions,
    layout: RunLayout,
    state: _State,
) -> None:
    futures: dict[Future[JobResult], JobInstance] = {}

    for inst in wave:
        upstream = _upstream(inst, state)
        blocked = _blocking_failure(inst, upstream)
        if blocked is not None:
            state.record(inst, _skipped(inst))
            _note(options, inst.key, f"skipped (not the vibe): {blocked}")
            continue

        # Per INSTANCE, not per run. `Contexts` is mutable and the jobs of a
        # wave run in parallel, so a shared object would let one leg read
        # another leg's matrix values. `for_instance` returns a fresh snapshot.
        contexts = for_instance(options.contexts, inst, upstream, state.job_of)

        ctx = JobContext(
            workspace=options.root,
            env=_job_env(options, contexts),
            secrets=options.masker,
            sink=options.sink,
            needs=upstream,
            event=options.event,
            contexts=contexts,
            run_id=layout.run_id,
        )
        futures[pool.submit(backend.run_job, inst, ctx)] = inst

    _collect(futures, options, state)


def _align_github_context(options: RunOptions, layout: RunLayout) -> None:
    """Make `${{ github.run_id }}` and `$GITHUB_RUN_ID` the same string.

    `build_github_context` mints a run id of its own when it cannot find one in
    the environment, and the executor's layout mints another for the log
    directory. Two ids for one run means `yeet logs <id>` cannot find what the
    workflow printed. The layout's id is the one on disk, so it wins.

    Safe to mutate here: this runs once, before the pool exists.
    """
    if options.contexts is None:
        return
    options.contexts.github["run_id"] = layout.run_id
    options.contexts.github.setdefault("workspace", str(options.root))


def _job_env(options: RunOptions, contexts: Contexts | None) -> dict[str, str]:
    """The env every step of this job starts from, above the backend's base.

    `github_env` finally has a call site — it was written in session 1 against
    the nine fields `build_github_context` promises and then went four sessions
    without one, which meant `${{ github.sha }}` resolved while `$GITHUB_SHA`
    did not. Two spellings of the same fact must not disagree inside one step.

    Workflow-level `env:` goes on top: it is the user's file, and it should win
    over anything we synthesised for them.
    """
    env: dict[str, str] = {}
    if contexts is not None:
        env.update(env_mod.github_env(contexts.github))
    env.update(options.env)
    env.update(env_mod.stringify_all(options.workflow_env))
    return env


def _collect(
    futures: dict[Future[JobResult], JobInstance],
    options: RunOptions,
    state: _State,
) -> None:
    """Wait for the wave. Fail-fast cancels siblings that have not started.

    Cancellation only reaches queued work — a leg already inside `run_job` has
    a live container and is left to finish and clean up after itself. Killing
    it mid-step is how you strand containers, which is the thing fail-fast is
    meant to be cheaper than.
    """
    cancelled_jobs: set[str] = set()

    for future, inst in futures.items():
        if inst.job.key in cancelled_jobs and future.cancel():
            state.record(inst, _skipped(inst))
            _note(options, inst.key, "cancelled (fail-fast)")
            continue

        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001 - a backend bug is that job's failure
            _note(options, inst.key, f"{type(exc).__name__}: {exc}")
            result = _failed(inst, f"{type(exc).__name__}: {exc}")

        state.record(inst, result)

        if result.status is Status.FAILURE and _fail_fast(inst):
            cancelled_jobs.add(inst.job.key)


def _fail_fast(inst: JobInstance) -> bool:
    strategy = inst.job.strategy
    return bool(strategy and strategy.fail_fast and strategy.matrix)


def _upstream(inst: JobInstance, state: _State) -> dict[str, JobResult]:
    """The `needs:` context: every finished instance of every job we depend on."""
    wanted = set(inst.job.needs)
    if not wanted:
        return {}
    return {
        key: result for key, result in state.results.items() if state.job_of.get(key, key) in wanted
    }


def _blocking_failure(inst: JobInstance, upstream: dict[str, JobResult]) -> str | None:
    """Why this job must not run, or None if it may."""
    if not inst.job.needs:
        return None
    if _wants_to_run_regardless(inst):
        return None
    broken = sorted(key for key, result in upstream.items() if not result.status.ok)
    if broken:
        return f"{', '.join(broken)} flopped"
    if not upstream:
        # E301 already reported an unknown `needs:` at validation time, so this
        # only happens when the planner put us in the wrong wave. Say so rather
        # than running a job whose inputs do not exist.
        return f"{', '.join(sorted(inst.job.needs))} never ran"
    return None


def _wants_to_run_regardless(inst: JobInstance) -> bool:
    condition = (inst.job.if_ or "").lower()
    return any(marker in condition for marker in ALWAYS_RUN_MARKERS)


def _skipped(inst: JobInstance) -> JobResult:
    """The reason is emitted as a META event rather than stored: JobResult is a
    frozen-by-agreement core type and a `skip_reason` field is a standup item,
    not a unilateral edit."""
    return JobResult(
        job_key=inst.key,
        matrix_leg=dict(inst.leg),
        status=Status.SKIPPED,
        steps=[StepResult(step_name=label(step), status=Status.SKIPPED) for step in inst.job.steps],
    )


def _failed(inst: JobInstance, reason: str) -> JobResult:
    return JobResult(
        job_key=inst.key,
        matrix_leg=dict(inst.leg),
        status=Status.FAILURE,
        steps=[StepResult(step_name=reason, status=Status.FAILURE, exit_code=1)],
    )


def _note(options: RunOptions, job_key: str, text: str) -> None:
    if options.sink is None:
        return
    options.sink.emit(
        LogEvent.now(job=job_key, step="", stream=META, text=options.masker.mask(text))
    )
