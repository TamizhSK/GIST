"""yeet graph — print the job DAG as waves of instances.

The heavy lifting is `build_plan`'s; this command is the validation gate and
rendering; discovery is `analyzer.discover`'s, shared with `scan` and `check`.
`render_plan` is a pure function so the tree can be tested without invoking the
CLI.

If the workflow cannot be built yet (Dev A's parser still landing), say so
clearly instead of pretending — a graph of nothing is a lie.

Owner: Dev B
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from yeet.analyzer.discover import discover_flows
from yeet.cli import EXIT_BAD_WORKFLOW
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Workflow
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import ExecutionPlan, build_plan
from yeet.validation.pipeline import validate_file


def graph(
    path: Annotated[Path, typer.Argument(help="Project directory or flow file.")] = Path(),
) -> None:
    """Print the job DAG: matrix legs expanded, waves topo-sorted.

    Runs validation layers 0-3 and refuses to draw an invalid workflow. Layer 4
    is lint-only and never blocks a graph.
    """
    target = path if path.exists() else Path.cwd()
    flows = _flows(target)

    if not flows:
        typer.secho(
            "No flows found. Try `yeet init --auto` to generate one.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(EXIT_BAD_WORKFLOW)

    for flow in flows:
        bag, workflow = validate_file(flow, upto=3)
        if bag.has_errors():
            _render_diagnostics(bag)
            raise typer.Exit(EXIT_BAD_WORKFLOW)

        if workflow is None:
            typer.secho(
                f"`{flow}` cannot be turned into a plan yet — the parser is not "
                "ready (Dev A). The file validates; the IR does not exist.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            raise typer.Exit(1)

        plan = build_plan(workflow, Contexts(env=dict(os.environ)))
        typer.echo(render_plan(workflow, plan))


def render_plan(wf: Workflow, plan: ExecutionPlan) -> str:
    """The tree. Deterministic, ASCII, and deliberately pre-execution: statuses
    belong to `yeet run`, not here."""
    lines = [f"flow: {wf.display_name}"]
    lines.append(f"{plan.total_jobs} job instance(s) in {len(plan.waves)} wave(s)")

    for index, wave in enumerate(plan.waves, start=1):
        lines.append(f"wave {index}")
        for inst in wave:
            suffix = f"   (needs: {', '.join(inst.job.needs)})" if inst.job.needs else ""
            lines.append(f"  * {inst.key}{suffix}")

    return "\n".join(lines) + "\n"


def _flows(target: Path) -> list[Path]:
    """Every flow in the project, in precedence order — or the file itself.

    `analyzer.discover`, the same walk `yeet scan` and `yeet check` use. This
    command had its own version that globbed `*.yml` in `.yeet/flows` and
    `.github/workflows` and stopped at the first of the two that matched, which
    got three things wrong: a project written in `.yaml` had no graph at all, a
    bare `workflows/` directory had no graph at all, and a monorepo's
    `packages/api/.github/workflows/ci.yml` was invisible because the glob is
    not recursive. `scan` listed those files and `graph` said "No flows found"
    about the same directory.

    Precedence now orders the list rather than truncating it: `.yeet/flows/`
    first, then `.github/workflows/`, then a bare `workflows/`, then a root
    `yeet.yml`. Every flow gets drawn, because a graph is a thing you read and
    hiding four of five flows is not a service.
    """
    if target.is_file():
        return [target]
    flows, _foreign = discover_flows(target)
    return flows


def _render_diagnostics(bag: DiagnosticBag) -> None:
    """`render_diagnostics` has its own `str(diagnostic)` fallback inside it
    (D5, risk #8), so there is nothing to catch here."""
    from yeet.reporting.render import render_diagnostics

    typer.echo(render_diagnostics(bag), err=True)
