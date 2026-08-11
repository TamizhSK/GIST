"""yeet run — the whole pipeline. Validates first; refuses on any error.

Wiring only. Every decision worth testing lives in `executor/runner.py`; this
file turns CLI flags into a `RunOptions` and turns a `RunResult` into an exit
code.

ON THE `_not_ready` BLOCKS BELOW. Four of the five stages this command drives
belong to other people and are still `NotImplementedError`. Each call is
wrapped so the user gets one actionable line instead of a traceback. **Owners:
delete the wrapper around your stage when you implement it** — they are marked
individually and none of them hides a bug in our own code, only an absent
module.

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from yeet.cli import EXIT_BAD_WORKFLOW, EXIT_NO_DOCKER
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.events import META, FanOut, LogEvent, LogSink
from yeet.core.ir import Workflow
from yeet.core.masking import Masker
from yeet.core.project import Project
from yeet.core.result import RunResult, Status
from yeet.executor.backend import Backend, DockerUnavailable
from yeet.executor.docker_backend import DockerBackend
from yeet.executor.images import ImageKind, ImageResolutionError, resolve_image
from yeet.executor.local_backend import LocalBackend
from yeet.executor.runner import RunOptions, run_plan
from yeet.executor.workspace import create
from yeet.expressions.contexts import Contexts, build_github_context
from yeet.planner.plan import ExecutionPlan, build_plan
from yeet.reporting.console import RunConsole
from yeet.validation.pipeline import validate_file

T = TypeVar("T")

EXIT_NOT_READY = 1
"""A stage of the pipeline is not implemented yet. Not EXIT_JOB_FAILED (nothing
ran) and not EXIT_BAD_WORKFLOW (the file may be perfectly fine)."""


def run(
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

    project = _stage("analyzer.project.analyze", "Dev A (A7)", lambda: _analyze(root))
    target = _pick_flow(project, flow)

    bag, workflow = _stage(
        "validation.pipeline.validate_file",
        "Dev D (D8)",
        lambda: validate_file(target, upto=4),
    )
    _gate(bag, target)
    if workflow is None:
        raise typer.Exit(EXIT_BAD_WORKFLOW)

    contexts = _contexts(root, event)
    plan = _stage("planner.plan.build_plan", "Dev B (B11)", lambda: build_plan(workflow, contexts))
    if job is not None:
        plan = _only(plan, job)

    masker = Masker()
    overrides = _parse_secrets(secret or [])
    masker.update(overrides.values())
    masker.update(_stage_optional("secrets.store.load_secrets", lambda: _load_secrets(root)))

    backend = _backend(root, project, workflow)
    options = RunOptions(
        root=root,
        workflow_name=workflow.display_name,
        event=event,
        max_workers=jobs or os.cpu_count(),
        masker=masker,
        sink=_sink(verbose),
        contexts=contexts,
        layout=create(root),
    )

    try:
        result = run_plan(plan, backend, options)
    except DockerUnavailable as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_NO_DOCKER) from exc

    _report(result)
    raise typer.Exit(result.exit_code)


# --- stages ------------------------------------------------------------------


def _analyze(root: Path) -> Project:
    from yeet.analyzer.project import analyze

    return analyze(root)


def _load_secrets(root: Path) -> dict[str, str]:
    """Dev D's store (D21). `secrets/store.py` is currently an empty file, so
    the function may not exist at all — hence getattr rather than a plain
    import, which would be an ImportError at module load and would take the
    whole command down."""
    import yeet.secrets.store as store

    loader = getattr(store, "load_secrets", None)
    if loader is None:
        raise NotImplementedError("secrets.store.load_secrets")
    loaded: dict[str, str] = loader(root, {})
    return loaded


def _contexts(root: Path, event: str) -> Contexts:
    """Dev B's contexts. Always a Contexts — an empty one is still usable.

    A missing `build_github_context` costs us the `github.*` values, not the
    ability to run: `interpolate` degrades loudly on the expressions it cannot
    evaluate and the rest of the workflow proceeds. That is what keeps the
    walking skeleton meaningful before B5 lands.
    """
    contexts = Contexts(env=dict(os.environ))
    try:
        contexts.github = dict(build_github_context(root, event))
    except NotImplementedError:
        contexts.github = {"event_name": event, "workspace": str(root)}
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


def _sink(verbose: bool) -> LogSink:
    """Dev D's live tree, plus a plain-text fallback and room for D23's store.

    FanOut counts a failing sink instead of raising, so an unimplemented
    `RunConsole.emit` costs us the pretty output and nothing else — the run
    still completes and still reports. `EchoSink` means there IS still output
    in the meantime, which is what makes the executor demonstrable today.
    """
    return FanOut(sinks=[RunConsole(), EchoSink(verbose=verbose)])


class EchoSink:
    """A `core.events.LogSink` that just prints. Temporary, and deliberately so.

    It exists because `reporting.console.RunConsole` (Dev D, D6) is still a
    stub: without it a run produces a container full of output and an empty
    terminal. Delete it when D6 lands.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose

    def emit(self, event: LogEvent) -> None:
        if event.stream == META and not self.verbose:
            return
        prefix = f"  {event.job} · " if event.job else "  "
        typer.echo(f"{prefix}{event.text}")


# --- helpers -----------------------------------------------------------------


def _stage(name: str, owner: str, call: Callable[[], T]) -> T:
    """Run one pipeline stage, or explain who owes us it.

    DELETE THE WRAPPER AT YOUR STAGE'S CALL SITE when you implement it.
    """
    try:
        return call()
    except NotImplementedError as exc:
        typer.secho(
            f"`yeet run` needs {name}, which is not implemented yet — owner: {owner}.\n"
            "See plan.md. The executor itself is ready; this is the seam above it.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(EXIT_NOT_READY) from exc


def _stage_optional(name: str, call: Callable[[], dict[str, str]]) -> dict[str, str]:
    """Same, for a stage we can do without. Missing secrets are not fatal."""
    try:
        return call()
    except NotImplementedError:
        typer.secho(
            f"{name} is not implemented yet — only --secret values will be masked.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return {}


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
        try:
            typer.echo(render_diagnostics(bag), err=True)
        except NotImplementedError:
            for diagnostic in bag.sorted():
                typer.echo(str(diagnostic), err=True)
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


def _report(result: RunResult) -> None:
    verdict = "slayed" if result.status is Status.SUCCESS else "flopped"
    typer.echo(
        f"\nflow: {result.workflow_name} — {verdict.upper()} in {result.duration_s:.1f}s "
        f"({len(result.jobs)} job(s), run {result.run_id})"
    )
