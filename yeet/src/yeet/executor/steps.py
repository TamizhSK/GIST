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
from typing import Protocol

from yeet.core.events import META, STDERR, STDOUT, LogEvent, LogSink
from yeet.core.ir import Job, Step
from yeet.core.masking import Masker
from yeet.core.result import JobResult, Status, StepResult
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
    base_env: dict[str, str]
    masker: Masker
    to_step_path: Callable[[Path], str]
    """Host path -> the path the step will see. `str` on the host,
    `paths.to_workspace_path` inside a container."""
    sink: LogSink | None = None
    contexts: Contexts | None = None
    in_container: bool = True
    degraded: Degradation = field(default_factory=Degradation)
    step_outputs: dict[str, dict[str, str]] = field(default_factory=dict)
    """`{step.id: {name: value}}` — what `steps.<id>.outputs.<k>` and a job's
    own `outputs:` block resolve against. Filled as the loop runs."""


def run_steps(config: StepLoopConfig, executor: StepExec) -> list[StepResult]:
    """Run every step of a job in order, one StepResult each.

    Stops at the first failure unless that step was `continue-on-error`. The
    remaining steps are still reported, as SKIPPED — a run report with silent
    gaps in it is worse than a long one.
    """
    results: list[StepResult] = []
    exported: dict[str, str] = {}
    path_entries: list[str] = []
    failed = False

    for index, step in enumerate(config.job.steps, start=1):
        name = label(step)

        if failed:
            results.append(StepResult(step_name=name, status=Status.SKIPPED))
            continue

        if not truthy(step.if_, config.contexts, config.degraded):
            _emit(config, name, META, "skipped (not the vibe): `if` was false")
            results.append(StepResult(step_name=name, status=Status.SKIPPED))
            continue

        if step.uses and not step.run:
            # Dev A's resolver (A17) expands `uses:` into runnable steps before
            # we ever see it. Until that lands, say so rather than pretend.
            _emit(config, name, META, f"`uses: {step.uses}` needs actions.resolver (Dev A, A17)")
            results.append(StepResult(step_name=name, status=Status.SKIPPED))
            continue

        result = _run_one(
            config,
            executor,
            step=step,
            index=index,
            exported=exported,
            path_entries=path_entries,
        )
        results.append(result)

        if result.status is Status.FAILURE and not step.continue_on_error:
            failed = True

    return results


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
    outputs = {
        name: expand(expression, config.contexts, config.degraded)
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
    exported: dict[str, str],
    path_entries: list[str],
) -> StepResult:
    name = label(step)
    started = time.monotonic()

    layout = config.layout.step(index, script_suffix(step.shell))
    files = state_files.prepare(layout.dir)
    write_step_script(expand(step.run, config.contexts, config.degraded), layout.script)

    request = StepRequest(
        argv=shell_argv(
            step.shell, config.to_step_path(layout.script), in_container=config.in_container
        ),
        env=_step_env(config, step, files, exported, path_entries),
        workdir=step.working_directory,
        timeout_s=step.timeout_minutes * 60 if step.timeout_minutes else None,
    )

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
    if step.id:
        config.step_outputs[step.id] = back[state_files.OUTPUT]

    status = Status.SUCCESS if exit_code == 0 else Status.FAILURE
    if status is Status.FAILURE and step.continue_on_error:
        _emit(config, name, META, f"flopped (exit {exit_code}) but `delulu: true` — carrying on")

    return StepResult(
        step_name=name,
        status=status,
        exit_code=exit_code,
        duration_s=time.monotonic() - started,
        outputs=dict(back[state_files.OUTPUT]),
    )


def _step_env(
    config: StepLoopConfig,
    step: Step,
    files: dict[str, Path],
    exported: dict[str, str],
    path_entries: list[str],
) -> dict[str, str]:
    """Layered lowest-precedence first. The order is the whole contract.

    base < what earlier steps exported < job env < step env < `with:` inputs.
    State-file paths are last because nothing may shadow them, and PATH is
    merged rather than replaced.
    """
    env = dict(config.base_env)
    env.update(exported)
    env.update(env_mod.stringify_all(config.job.env))
    env.update(env_mod.stringify_all(step.env))
    env.update(env_mod.input_env(step.with_))
    env = {key: expand(value, config.contexts, config.degraded) for key, value in env.items()}
    env.update(env_mod.state_file_env(files, to_path=config.to_step_path))
    env_mod.merge_path(env, path_entries)
    return env


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
