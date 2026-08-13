"""yeet run — the whole pipeline. Validates first; refuses on any error.

Wiring only. Every decision worth testing lives in `executor/runner.py`; this
file turns CLI flags into a `RunOptions` and turns a `RunResult` into an exit
code.

This command used to wrap each of its five stages in a `_stage()` helper that
caught `NotImplementedError` and named the owner who still owed us the module.
All five have landed, so the wrappers are gone: a `NotImplementedError` from a
finished module is a bug and should look like one, not like an unfinished
hand-off. The same goes for `EchoSink` (superseded by `RunConsole`) and
`EXIT_NOT_READY` (which shared the value 1 with `EXIT_JOB_FAILED`).

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import EXIT_BAD_WORKFLOW, EXIT_NO_DOCKER, color_enabled
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.events import FanOut
from yeet.core.ir import Workflow
from yeet.core.masking import Masker
from yeet.core.project import Project
from yeet.executor.backend import Backend, DockerUnavailable
from yeet.executor.docker_backend import DockerBackend
from yeet.executor.images import ImageKind, ImageResolutionError, resolve_image
from yeet.executor.local_backend import LocalBackend
from yeet.executor.runner import RunOptions, run_plan
from yeet.executor.workspace import create
from yeet.expressions.contexts import Contexts, build_github_context
from yeet.planner.plan import ExecutionPlan, build_plan
from yeet.reporting.live import make_console
from yeet.storage.runs import RunStore
from yeet.validation.pipeline import validate_file


def run(
    ctx: typer.Context,
    flow: Annotated[str | None, typer.Argument(help="Flow name. Default: all discovered.")] = None,
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    job: Annotated[str | None, typer.Option("--job", help="Run one job only.")] = None,
    event: Annotated[str, typer.Option("--event", help="Simulate a trigger.")] = "push",
    jobs: Annotated[int | None, typer.Option("--jobs", help="Max parallel jobs.")] = None,
    secret: Annotated[
        list[str] | None, typer.Option("--secret", help="K=V, highest precedence.")
    ] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
) -> None:
    """Analyze -> validate -> plan -> execute -> report.

    Layers 0-3 run and HARD STOP on any error before a container is created
    (exit 2). Layer 4 runs and prints but never blocks. That gate is the whole
    reason this tool is safe to point at a repo you did not write.
    """
    root = path.resolve()

    project = _analyze(root)
    target = _pick_flow(project, flow)

    bag, workflow = validate_file(target, upto=4)
    _gate(bag, target)
    if workflow is None:
        raise typer.Exit(EXIT_BAD_WORKFLOW)

    # Secrets are resolved BEFORE the contexts are built, because they are one
    # of the contexts. `--secret K=V` wins over the store, which wins over
    # `.env` — `load_secrets` owns that precedence.
    secrets = _load_secrets(root, _parse_secrets(secret or []))

    masker = Masker()
    masker.update(secrets.values())

    contexts = _contexts(root, event, secrets)
    plan = build_plan(workflow, contexts)
    if job is not None:
        plan = _only(plan, job)
    if verbose:
        _echo_plan(plan)

    # The layout is created here rather than inside `run_plan` because its
    # run_id is what names this run's log directory, and the sink needs that
    # id before the first event is emitted.
    layout = create(root)

    backend = _backend(root, project, workflow)
    # `make_console` picks the live tree for a real terminal, plain lines
    # otherwise. Either way it sits beside `RunStore` in a `FanOut`, which is
    # what makes `.yeet/runs/` non-empty and `yeet logs` able to answer —
    # both halves of that were written independently and only wired together
    # here. A failing sink is counted, not raised: a full disk should cost the
    # log file, not the run.
    console_sink = make_console(color=color_enabled(ctx), verbose=verbose)
    options = RunOptions(
        root=root,
        workflow_name=workflow.display_name,
        event=event,
        max_workers=jobs or os.cpu_count(),
        workflow_env=dict(workflow.env),
        masker=masker,
        sink=FanOut(sinks=[console_sink, RunStore(layout.root, layout.run_id)]),
        contexts=contexts,
        layout=layout,
    )

    # `console_sink` owns a `rich.live.Live` region on a real terminal (a
    # no-op start/stop on a plain pipe) — it has to be open for the whole run
    # so events streaming in from the runner's thread pool land in it, and
    # closed before anything else touches the terminal, success or not.
    console_sink.start()
    try:
        result = run_plan(plan, backend, options)
    except DockerUnavailable as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_NO_DOCKER) from exc
    finally:
        console_sink.stop()

    console_sink.render_summary(
        result.workflow_name,
        result.status.value,
        result.duration_s,
        run_id=result.run_id,
        job_count=len(result.jobs),
    )
    raise typer.Exit(result.exit_code)


# --- stages ------------------------------------------------------------------


def _analyze(root: Path) -> Project:
    from yeet.analyzer.project import analyze

    return analyze(root)


def _load_secrets(root: Path, overrides: dict[str, str]) -> dict[str, str]:
    """Everything `secrets/store.py` can find, plus `--secret` on top.

    A locked store is not fatal: most workflows need no secrets, and refusing
    to run because a passphrase is absent would make the encryption everyone's
    problem rather than only the problem of people who use it. It is said out
    loud, though — a run that silently masked nothing would be worse than
    either. `--secret` values still apply in that case.
    """
    from yeet.secrets.store import SecretsError, SecretsLocked, load_secrets

    try:
        return load_secrets(root, overrides)
    except SecretsLocked as exc:
        typer.secho(
            f"{exc} Running with --secret values and .env only.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    except SecretsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
    return dict(overrides)


def _contexts(root: Path, event: str, secrets: dict[str, str]) -> Contexts:
    """The RUN-WIDE contexts for `${{ }}` — the ones that cannot vary per job.

    `secrets` is passed in rather than left empty: `Contexts` has had the field
    since B5, but nothing populated it, so `${{ secrets.NPM_TOKEN }}` evaluated
    to nothing and a step's `drip:`/`env:` got an empty string. The values were
    reaching the `Masker` (so nothing leaked) and never reaching the workflow —
    which looks exactly like a masking success until you check the exit code of
    the thing that needed the token.

    That was one of six fields with the same disease. `matrix`, `needs`, `job`,
    `env`, `steps` and `runner` all vary per job instance or per step, so they
    cannot be filled here and are filled by `executor/contexts.py` instead —
    `for_instance` in the runner, `for_step` in the step loop. What is built
    here is only what is true for the whole run.
    """
    contexts = Contexts(env=dict(os.environ))
    contexts.root = root
    contexts.github = dict(build_github_context(root, event))
    contexts.secrets = dict(secrets)
    return contexts


def _backend(root: Path, project: Project, workflow: Workflow) -> Backend:
    """Docker unless every job asked for `cooked_on: local`.

    Deciding once, up front, means a project that cannot reach a daemon but
    only runs local jobs never touches the SDK at all.
    """
    kinds = set()
    for job in workflow.jobs.values():
        try:
            kinds.add(resolve_image(job, project).kind)
        except ImageResolutionError:
            kinds.add(ImageKind.BASE)
    if kinds and kinds <= {ImageKind.LOCAL}:
        return LocalBackend(root)
    return DockerBackend(root, project=project)


def _echo_plan(plan: ExecutionPlan) -> None:
    """`-v`: what we are about to do, before we do it."""
    total = sum(len(wave) for wave in plan.waves)
    typer.echo(f"plan: {total} job instance(s) in {len(plan.waves)} wave(s)", err=True)
    for number, wave in enumerate(plan.waves, start=1):
        typer.echo(f"  wave {number}: {', '.join(inst.key for inst in wave)}", err=True)


# --- helpers -----------------------------------------------------------------


def _pick_flow(project: Project, flow: str | None) -> Path:
    if not project.flows:
        typer.secho(
            "No flows found. Try `yeet init --auto` to generate one.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(EXIT_BAD_WORKFLOW)
    if flow is None:
        return project.flows[0]
    for candidate in project.flows:
        if flow in (candidate.name, candidate.stem):
            return candidate
    typer.secho(f"No flow named `{flow}`.", fg=typer.colors.RED, err=True)
    raise typer.Exit(EXIT_BAD_WORKFLOW)


def _gate(bag: DiagnosticBag, source: Path) -> None:
    """The gate. Errors stop the run BEFORE any container exists.

    Warnings (layer 4) print and never block — that is the difference between a
    tool people keep pointed at their repo and one they turn off.
    """
    from yeet.reporting.render import render_diagnostics

    if len(bag):
        typer.echo(render_diagnostics(bag), err=True)
    if bag.has_errors():
        typer.secho(
            f"{len(bag.errors)} error(s) in {source} — refusing to run.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(EXIT_BAD_WORKFLOW)


def _only(plan: ExecutionPlan, job: str) -> ExecutionPlan:
    """`--job build` — keep that job's instances and drop the rest."""
    waves = [[inst for inst in wave if job in (inst.key, inst.job.key)] for wave in plan.waves]
    return ExecutionPlan(waves=[wave for wave in waves if wave])


def _parse_secrets(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if sep and key.strip():
            out[key.strip()] = value
    return out

