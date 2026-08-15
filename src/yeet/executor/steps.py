"""The per-step loop. Shared by both backends; only *how you exec* differs.

WHY THIS FILE EXISTS (it is not in plan.md's file list). Write the script,
assemble the environment, run it, split the byte stream into lines, mask, parse
`::` directives, emit, read the state files back, decide the status — every one
of those is identical for Docker and for the host shell. The only difference is
one call. Written twice, the two backends drift, and the local one (which is
what most tests use) stops being evidence about the Docker one.

It is also risk #11's chokepoint: `_emit` below is the ONLY place in the
executor that constructs a LogEvent, so it is the only place masking has to be
applied. There is no second code path to forget.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from yeet.core.builtins import BuiltinContext, BuiltinResult, BuiltinRunner
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.events import META, STDERR, STDOUT, LogEvent, LogSink
from yeet.core.ir import Job, Step
from yeet.core.masking import Masker
from yeet.core.result import JobResult, Status, StepResult
from yeet.executor import contexts as ctx_mod
from yeet.executor import env as env_mod
from yeet.executor import state_files
from yeet.executor.commands import (
    ADD_MASK,
    DEBUG,
    ENDGROUP,
    ERROR,
    GROUP,
    NOTICE,
    WARNING,
    Command,
    parse_workflow_command,
)
from yeet.executor.interpolate import DEGRADED_NOTE, Degradation, expand, truthy
from yeet.executor.paths import CONTAINER_JOB_DIR, CONTAINER_WORKSPACE
from yeet.executor.script import script_suffix, shell_argv, write_step_script
from yeet.executor.workspace import JobLayout
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import JobInstance

Chunk = tuple[str, bytes]
"""(stream, bytes) where stream is core.events.STDOUT or STDERR."""

TIMEOUT_EXIT_CODE = 124
"""What `timeout(1)` uses. Distinct from 1 so a report can tell the two apart."""

LABEL_MAX = 60


def label(step: Step) -> str:
    """The one-line name a step is logged under.

    NOT `Step.display_name`, which falls back to the whole of `run:`. That is
    the right answer for a diagnostic (it identifies the step in the file) and
    the wrong one for a log line: a twenty-line script becomes a twenty-line
    group header, and every line after the first is emitted before the Masker
    has seen anything the step produced. GitHub shows `Run <first line>` for
    the same reason.
    """
    if step.name:
        return step.name
    if step.run:
        first = step.run.strip().splitlines()[0] if step.run.strip() else ""
        trimmed = first[: LABEL_MAX - 1] + "…" if len(first) > LABEL_MAX else first
        return f"Run {trimmed}" if trimmed else "Run"
    if step.uses:
        return step.uses
    return "<unnamed step>"


@dataclass(frozen=True, slots=True)
class StepRequest:
    """Everything a backend needs in order to actually run one script."""

    argv: list[str]
    env: dict[str, str]
    workdir: str | None = None
    timeout_s: float | None = None


class StepExec(Protocol):
    """The one thing the two backends implement differently."""

    def exec_step(self, request: StepRequest) -> tuple[int, Iterable[Chunk]]: ...


@dataclass
class StepLoopConfig:
    """Everything that stays the same across the steps of one job."""

    job: Job
    job_key: str
    layout: JobLayout
    root: Path
    """The PROJECT root — where `.yeet/artifacts/` and `.yeet/runs/` live. Not
    necessarily where the steps run: see `workspace`."""
    base_env: dict[str, str]
    masker: Masker
    to_step_path: Callable[[Path], str]
    """Host path -> the path the step will see. `str` on the host,
    `paths.to_workspace_path` inside a container."""
    workspace: Path | None = None
    """Where the steps actually run, on the host side of the mount. None means
    "the project root", which is every run that is not `--clean`.

    Optional so the many tests that build a StepLoopConfig by hand are
    unaffected; read it as `config.job_workspace`, never directly."""
    offline: bool = False
    """`yeet run --offline` — a `uses:` may be served from the action cache but
    may not fetch. Off by default: a remote action that has never been fetched
    cannot run any other way."""
    sink: LogSink | None = None
    contexts: Contexts | None = None
    in_container: bool = True
    builtins: BuiltinRunner | None = None
    """Runs `actions/cache` and friends. Injected by `cli/cmd_run` because the
    tier contract forbids the executor importing `storage` — see
    `core/builtins.py`."""
    degraded: Degradation = field(default_factory=Degradation)
    step_outputs: dict[str, dict[str, str]] = field(default_factory=dict)
    """`{step.id: {name: value}}` — what `steps.<id>.outputs.<k>` and a job's
    own `outputs:` block resolve against. Filled as the loop runs."""
    step_conclusions: dict[str, str] = field(default_factory=dict)
    """`{step.id: "success"|"failure"|"skipped"}` — the other half of the
    `steps` context. GitHub's words, not the console's: workflows in the wild
    are written against `steps.x.conclusion == 'success'`."""

    @property
    def job_workspace(self) -> Path:
        """Where the steps run. The root unless this job was isolated."""
        return self.workspace or self.root

    @property
    def isolated(self) -> bool:
        """True when the workspace is NOT the user's working tree."""
        return self.job_workspace.resolve() != self.root.resolve()


def run_steps(config: StepLoopConfig, executor: StepExec) -> list[StepResult]:
    """Run every step of a job in order, one StepResult each.

    Stops at the first failure unless that step was `continue-on-error`. The
    remaining steps are still reported, as SKIPPED — a run report with silent
    gaps in it is worse than a long one.
    """
    results: list[StepResult] = []
    exported: dict[str, str] = {}
    path_entries: list[str] = []
    post: list[Callable[[], None]] = []
    failed = False

    # A composite `uses:` splices its own steps in at this point, so the list
    # is walked as a queue rather than iterated: inlining while iterating a
    # list you are also appending to is how a composite action silently runs
    # twice.
    queue: list[Step] = list(config.job.steps)
    index = 0

    while queue:
        step = queue.pop(0)
        index += 1
        name = label(step)

        if failed:
            _lifecycle_skip(config, name)
            _conclude(config, step, Status.SKIPPED)
            results.append(StepResult(step_name=name, status=Status.SKIPPED))
            continue

        # Built per step, before `if:` is evaluated: the condition is entitled
        # to see `matrix`, `needs`, `env` and the outputs of earlier steps, and
        # every one of those was empty when a single run-wide Contexts was
        # threaded straight through from `cmd_run`.
        step_ctx, step_env = _step_contexts(config, step, exported)

        if not truthy(step.if_, step_ctx, config.degraded):
            _lifecycle_skip(config, name)
            _emit(config, name, META, "skipped (not the vibe): `if` was false")
            _conclude(config, step, Status.SKIPPED)
            results.append(StepResult(step_name=name, status=Status.SKIPPED))
            continue

        if step.uses and not step.run:
            outcome = _run_uses(config, step, name, post, step_ctx)
            if isinstance(outcome, list):
                queue[:0] = outcome  # a composite: run its steps in its place
                index -= 1  # the `uses:` line is not itself a step that ran
                continue
            results.append(outcome)
            if outcome.status is Status.FAILURE and not step.continue_on_error:
                failed = True
            continue

        result = _run_one(
            config,
            executor,
            step=step,
            index=index,
            contexts=step_ctx,
            step_env=step_env,
            exported=exported,
            path_entries=path_entries,
        )
        results.append(result)

        if result.status is Status.FAILURE and not step.continue_on_error:
            failed = True

    # POST actions, newest first — GitHub's order, and the one that matters:
    # a cache registered by a later step is saved before one registered
    # earlier, so an inner cache cannot be clobbered by an outer one. They run
    # even when the job failed, because a cache of a half-finished build is
    # still worth more than no cache, and an artifact of a failed run is often
    # the only evidence of why it failed.
    for action in reversed(post):
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - a post action must not mask the job's result
            _emit(config, "post", META, f"post action failed: {exc!r}")

    return results


def _run_uses(
    config: StepLoopConfig,
    step: Step,
    name: str,
    post: list[Callable[[], None]],
    contexts: Contexts | None,
) -> list[Step] | StepResult:
    """A `uses:` step: inline it, run a built-in, or skip it with a reason.

    A list means "run these in my place"; a StepResult means this step is
    finished. Resolution happens exactly once — returning the steps rather
    than a "go inline it" signal is what stops the caller from resolving a
    second time and emitting every E313/W319 twice.
    """
    from yeet.executor import uses as uses_mod

    bag = DiagnosticBag()
    # A local `uses: ./x` resolves against the WORKSPACE, as it does on GitHub —
    # under `--clean` that is the tree `actions/checkout` just placed, and a
    # workflow that never checked out is meant to fail here rather than reach
    # into a working tree the job was never given.
    plan = uses_mod.plan_uses(
        step,
        config.job_workspace,
        bag,
        offline=config.offline,
        # Announced on the STEP's own line rather than once at startup: the
        # user needs to know which `uses:` went to the network, and a run that
        # pauses for ten seconds should say what it is waiting for.
        on_fetch=lambda uses: _emit(config, name, META, f"fetching {uses} into the action cache"),
    )

    for diagnostic in bag.items:
        _emit(config, name, META, f"{diagnostic.code}: {diagnostic.message}")

    if plan.kind == uses_mod.INLINE:
        if bag.has_errors():
            _emit(config, name, META, f"`{step.uses}` could not be prepared")
            _conclude(config, step, Status.FAILURE)
            return StepResult(step_name=name, status=Status.FAILURE, exit_code=1)
        # GitHub propagates `continue-on-error` into a composite's steps but
        # not `if:` — the caller's condition was already evaluated above.
        for inner in plan.steps:
            inner.continue_on_error = inner.continue_on_error or step.continue_on_error
        return plan.steps

    if plan.kind == uses_mod.BUILTIN:
        return _run_builtin(config, step, name, plan, post, contexts)

    if plan.blocking:
        # Not skipped: we could not GET the action. The workflow says to run
        # it and GitHub would, so a green run here would be a lie of exactly
        # the kind `continue-on-error` exists to make deliberate.
        # Start/end pair, as `_lifecycle_skip` does: the live tree creates a
        # node on the first event it sees and resolves it on STEP_END, so an
        # end without a start leaves a step that never stops spinning.
        _step_started(config, name)
        _emit(config, name, META, plan.reason)
        _conclude(config, step, Status.FAILURE)
        _step_ended(config, name, Status.FAILURE, 0.0, 1)
        return StepResult(step_name=name, status=Status.FAILURE, exit_code=1)

    _emit(config, name, META, f"skipped (not the vibe): {plan.reason}")
    _conclude(config, step, Status.SKIPPED)
    return StepResult(step_name=name, status=Status.SKIPPED)


def _run_builtin(
    config: StepLoopConfig,
    step: Step,
    name: str,
    plan: Any,
    post: list[Callable[[], None]],
    contexts: Contexts | None,
) -> StepResult:
    """Invoke the built-in through the runner the CLI handed us.

    Not imported: `storage` is the executor's SIBLING and the tier contract
    forbids the edge (docs/adr/0007). `cmd_run` passes
    `storage.builtin.run_builtin` down, exactly as it passes a `LogSink` and a
    `Masker`. When no runner was supplied — every unit test that does not care
    about artifacts — the step is skipped and says so.
    """
    if config.builtins is None:
        _lifecycle_skip(config, name)
        _emit(config, name, META, f"skipped (not the vibe): no runner for `{plan.builtin}`")
        _conclude(config, step, Status.SKIPPED)
        return StepResult(step_name=name, status=Status.SKIPPED)

    started = time.monotonic()
    # A built-in is a step like any other as far as a renderer is concerned.
    # Without these the live tree creates the node on its first output line,
    # marks it RUNNING, and never hears that it finished — so `checkout` sat
    # under a spinner for the rest of the run while its result scrolled past
    # above it.
    _step_started(config, name)
    _emit(config, name, META, f"::group::{name}")
    ctx = BuiltinContext(
        root=config.root,
        run_id=config.layout.run_id,
        # The host side of whatever the backend bind-mounted at /workspace, so
        # a file the container just wrote is visible here at the same relative
        # path. Usually the project root; under `--clean` this job's own
        # directory, and passing the root there would have had
        # `upload-artifact` collect files from the working tree rather than
        # from what the job actually built.
        workspace=config.job_workspace,
        isolated=config.isolated,
        inputs=_expanded_with(config, step, contexts),
        emit=lambda line: _emit(config, name, STDOUT, line),
        post=post,
    )
    try:
        outcome = config.builtins(plan.builtin, ctx)
    except Exception as exc:  # noqa: BLE001 - report, never hide (see interpolate)
        _emit(config, name, META, f"`{plan.builtin}` failed: {exc!r}")
        outcome = BuiltinResult(ok=False, message=repr(exc))
    _emit(config, name, META, "::endgroup::")

    if step.id:
        config.step_outputs.setdefault(step.id, {}).update(outcome.outputs)

    status = Status.SUCCESS if outcome.ok else Status.FAILURE
    if not outcome.ok and outcome.message:
        _emit(config, name, META, outcome.message)
    _conclude(config, step, status)
    _step_ended(config, name, status, time.monotonic() - started, 0 if outcome.ok else 1)
    return StepResult(
        step_name=name,
        status=status,
        exit_code=0 if outcome.ok else 1,
        duration_s=time.monotonic() - started,
    )


def _expanded_with(
    config: StepLoopConfig, step: Step, contexts: Contexts | None
) -> dict[str, object]:
    """`with:` with its `${{ }}` resolved, for a built-in action.

    The run path gets this for free — `_layered_env` expands every value on its
    way out — but a built-in never becomes an environment, so its inputs were
    handed over raw. A matrix of two legs therefore uploaded both artifacts
    under the single literal name `out-${{ matrix.leg }}` and shared one cache
    key: the second leg overwrote the first, and the log said so in a string
    the user could read and still not notice.

    Then translated back out of the CONTAINER's filesystem, because a built-in
    runs on the host. A real action computes its paths from `${{ runner.temp }}`
    or `$GITHUB_WORKSPACE`, both of which are `/workspace/...` inside the job —
    a path that exists nowhere on this machine. `actions/upload-pages-artifact`
    hands `upload-artifact` exactly such a path, and the result was "no files
    matched" for a file that had just been written successfully.
    """
    expanded = {
        key: expand(value, contexts, config.degraded) if isinstance(value, str) else value
        for key, value in step.with_.items()
    }
    if not config.in_container:
        return expanded
    return {
        key: _to_host_path(value, config) if isinstance(value, str) else value
        for key, value in expanded.items()
    }


def _to_host_path(value: str, config: StepLoopConfig) -> str:
    """`/workspace/x` -> `<workspace>/x`, line by line. Anything else untouched.

    Line by line because `path:` is a multi-line string in every real workflow
    that uses it, and only some of those lines are absolute container paths.
    """
    if CONTAINER_WORKSPACE not in value and CONTAINER_JOB_DIR not in value:
        return value
    mounts = ((CONTAINER_WORKSPACE, config.job_workspace), (CONTAINER_JOB_DIR, config.layout.dir))
    out: list[str] = []
    for line in value.splitlines():
        text = line.strip()
        for mount, host in mounts:
            if text == mount:
                text = str(host)
                break
            if text.startswith(mount + "/"):
                text = str(host / text[len(mount) + 1 :])
                break
        out.append(text)
    return "\n".join(out)


def _conclude(config: StepLoopConfig, step: Step, status: Status) -> None:
    """Record a step's outcome under its `id:` for the `steps` context."""
    if step.id:
        config.step_conclusions[step.id] = ctx_mod.RESULT_WORDS.get(status, "failure")
        config.step_outputs.setdefault(step.id, {})


def _step_contexts(
    config: StepLoopConfig, step: Step, exported: dict[str, str]
) -> tuple[Contexts | None, dict[str, str]]:
    """The contexts this step evaluates against, and the env it will run with.

    Two passes, because `env:` values may themselves contain `${{ }}`. The
    first builds a context WITHOUT this step's env so those values have
    something to resolve against; the second feeds the resulting environment
    back in, so that inside one step `${{ env.FOO }}` and `$FOO` agree.
    """
    pre = ctx_mod.for_step(
        config.contexts,
        env=config.base_env,
        base_env=config.base_env,
        step_outputs=config.step_outputs,
        step_conclusions=config.step_conclusions,
        action_inputs=step.action_inputs,
    )
    env = _layered_env(config, step, exported, pre)
    full = ctx_mod.for_step(
        config.contexts,
        env=env,
        base_env=config.base_env,
        step_outputs=config.step_outputs,
        step_conclusions=config.step_conclusions,
        action_inputs=step.action_inputs,
    )
    return full, env


def build_job_result(
    config: StepLoopConfig, inst: JobInstance, results: list[StepResult], started: float
) -> JobResult:
    """Turn a finished step list into a JobResult. Shared by both backends.

    Also the one place the interpolation degradation is reported — once per
    job, at the end, so it is the last thing in the log rather than lost above
    a hundred lines of build output.
    """
    if config.degraded.hit:
        _emit(config, "", META, DEGRADED_NOTE)

    status = (
        Status.FAILURE if any(step.status is Status.FAILURE for step in results) else Status.SUCCESS
    )

    # A job's `outputs:` block is written almost exclusively in terms of
    # `steps.<id>.outputs.<name>`, so it has to be expanded against the context
    # as it stands AFTER the last step — not against the run-wide one, where
    # `steps` is permanently empty and every declared output was "".
    # No `action_inputs` here: a job's `outputs:` block is the WORKFLOW's, so
    # `${{ inputs.x }}` in it means the workflow's input, never some inlined
    # action's.
    final = ctx_mod.for_step(
        config.contexts,
        env=config.base_env,
        base_env=config.base_env,
        step_outputs=config.step_outputs,
        step_conclusions=config.step_conclusions,
    )
    outputs = {
        name: expand(expression, final, config.degraded)
        for name, expression in config.job.outputs.items()
    }
    return JobResult(
        job_key=inst.key,
        matrix_leg=dict(inst.leg),
        status=status,
        steps=results,
        outputs=outputs,
        duration_s=time.monotonic() - started,
    )


def _run_one(
    config: StepLoopConfig,
    executor: StepExec,
    *,
    step: Step,
    index: int,
    contexts: Contexts | None,
    step_env: dict[str, str],
    exported: dict[str, str],
    path_entries: list[str],
) -> StepResult:
    name = label(step)
    started = time.monotonic()

    layout = config.layout.step(index, script_suffix(step.shell, in_container=config.in_container))
    files = state_files.prepare(layout.dir)
    write_step_script(expand(step.run, contexts, config.degraded), layout.script)

    request = StepRequest(
        argv=shell_argv(
            step.shell, config.to_step_path(layout.script), in_container=config.in_container
        ),
        env=_with_state_files(config, files, step_env, path_entries),
        workdir=step.working_directory,
        timeout_s=step.timeout_minutes * 60 if step.timeout_minutes else None,
    )

    _step_started(config, name)
    _emit(config, name, META, f"::group::{name}")
    try:
        exit_code, stream = executor.exec_step(request)
        _pump(config, name, stream)
    except TimeoutError:
        _emit(config, name, META, f"timed out after {step.timeout_minutes} min")
        exit_code = TIMEOUT_EXIT_CODE
    except Exception as exc:  # noqa: BLE001 - a backend failure is a step failure
        _emit(config, name, STDERR, f"{type(exc).__name__}: {exc}")
        exit_code = 1
    finally:
        _emit(config, name, META, "::endgroup::")

    back = state_files.read_back(layout.dir)
    exported.update(back[state_files.ENV])
    path_entries.extend(state_files.path_entries(back))

    status = Status.SUCCESS if exit_code == 0 else Status.FAILURE
    if step.id:
        config.step_outputs[step.id] = back[state_files.OUTPUT]
    _conclude(config, step, status)

    if status is Status.FAILURE and step.continue_on_error:
        _emit(config, name, META, f"flopped (exit {exit_code}) but `delulu: true` — carrying on")

    duration_s = time.monotonic() - started
    _step_ended(config, name, status, duration_s, exit_code)

    return StepResult(
        step_name=name,
        status=status,
        exit_code=exit_code,
        duration_s=duration_s,
        outputs=dict(back[state_files.OUTPUT]),
    )


def _layered_env(
    config: StepLoopConfig,
    step: Step,
    exported: dict[str, str],
    contexts: Contexts | None,
) -> dict[str, str]:
    """Layered lowest-precedence first. The order is the whole contract.

    base (which now carries the workflow-level `env:`, applied by the runner)
    < what earlier steps exported < job env < step env < `with:` inputs.

    Split from the state-file paths below so that the result can be handed to
    `contexts.for_step` before the step runs: `env:` has to be resolvable from
    `${{ env.X }}` and from `$X`, and it can only be both if one dict feeds
    both.
    """
    env = dict(config.base_env)
    env.update(exported)
    env.update(env_mod.stringify_all(config.job.env))
    env.update(env_mod.stringify_all(step.env))
    env.update(env_mod.input_env(step.with_))
    return {key: expand(value, contexts, config.degraded) for key, value in env.items()}


def _with_state_files(
    config: StepLoopConfig,
    files: dict[str, Path],
    env: dict[str, str],
    path_entries: list[str],
) -> dict[str, str]:
    """State-file paths last, because nothing may shadow them; PATH is merged.

    These are deliberately NOT in the `env` context: `$GITHUB_ENV` names a
    scratch file that exists for the length of one step, and a workflow reading
    `${{ env.GITHUB_ENV }}` would be reading an implementation detail of ours.
    """
    out = dict(env)
    out.update(env_mod.state_file_env(files, to_path=config.to_step_path))
    env_mod.merge_path(out, path_entries)
    return out


def _pump(config: StepLoopConfig, step_name: str, stream: Iterable[Chunk]) -> None:
    """Byte chunks in, whole masked lines out.

    demux hands back arbitrary chunks, not lines. Masking half a line would let
    a secret split across two reads through unredacted, and `::add-mask::` only
    means anything if we see the whole directive — so the split happens here,
    once, before anything else looks at the text.
    """
    for stream_name, line in _lines(stream):
        command = parse_workflow_command(line)
        if command is not None and _handle_command(config, step_name, command):
            continue
        _emit(config, step_name, stream_name, line)


def _lines(stream: Iterable[Chunk]) -> Iterator[tuple[str, str]]:
    buffers: dict[str, bytes] = {STDOUT: b"", STDERR: b""}
    for name, chunk in stream:
        if not chunk:
            continue
        pending = buffers.get(name, b"") + chunk
        parts = pending.split(b"\n")
        buffers[name] = parts.pop()
        for raw in parts:
            yield name, raw.decode("utf-8", errors="replace").rstrip("\r")
    for name, tail in buffers.items():
        if tail:
            yield name, tail.decode("utf-8", errors="replace").rstrip("\r")


def _handle_command(config: StepLoopConfig, step_name: str, command: Command) -> bool:
    """Act on a `::` directive. True means "handled, do not also print it"."""
    if command.name == ADD_MASK:
        # Immediately, and before this line is emitted: a step that mints a
        # token at runtime must have it redacted from the very next line on.
        config.masker.add(command.value)
        _emit(config, step_name, META, "::add-mask:: registered a new secret")
        return True

    if command.name in (GROUP, ENDGROUP):
        _emit(config, step_name, META, f"::{command.name}::{command.value}")
        return True

    if command.name in (ERROR, WARNING, NOTICE, DEBUG):
        where = command.params.get("file")
        location = f" ({where}:{command.params.get('line', '?')})" if where else ""
        _emit(config, step_name, META, f"{command.name}: {command.value}{location}")
        return True

    return False


def _step_started(config: StepLoopConfig, step_name: str) -> None:
    """Tells a live renderer "this step now exists and is running" before the
    first line of its output arrives — the tree node (and its spinner) should
    not have to wait on `::group::` to know the step started."""
    if config.sink is None:
        return
    config.sink.emit(LogEvent.step_started(config.job_key, step_name))


def _step_ended(
    config: StepLoopConfig, step_name: str, status: Status, duration_s: float, exit_code: int | None
) -> None:
    if config.sink is None:
        return
    config.sink.emit(
        LogEvent.step_ended(
            config.job_key,
            step_name,
            status=status.value,
            duration_s=duration_s,
            exit_code=exit_code,
        )
    )


def _lifecycle_skip(config: StepLoopConfig, step_name: str) -> None:
    """A step that never ran (its `if:` was false, an upstream step flopped, or
    it needs a resolver we don't have) still gets a start/end pair, so the tree
    shows a skipped node instead of nothing."""
    _step_started(config, step_name)
    _step_ended(config, step_name, Status.SKIPPED, 0.0, None)


def _emit(config: StepLoopConfig, step_name: str, stream: str, text: str) -> None:
    """THE chokepoint. Every LogEvent in the executor is built right here.

    Masking is applied once, at the single point of emission (risk #11). There
    is deliberately no other LogEvent constructor in this package: a second one
    is a second place to forget, and what you forget is a secret.
    """
    if config.sink is None:
        return
    config.sink.emit(
        LogEvent.now(
            job=config.job_key,
            step=step_name,
            stream=stream,
            text=config.masker.mask(text),
        )
    )
