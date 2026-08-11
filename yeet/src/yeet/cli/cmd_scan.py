"""yeet scan — the §3.9 report block: project line, stack, markers, flows found
with per-flow validity (validate_file upto=2), and the Dockerfile hint.

Zero flows is NOT an error: print the fingerprint and suggest `yeet init
--auto`. That is what makes "point it at any repo" true.

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from yeet.analyzer.project import analyze
from yeet.core.project import Project
from yeet.validation.pipeline import validate_file

_OK = "✔"
_BAD = "✖"
_SKIP = "~"


def _color_enabled(ctx: typer.Context | None) -> bool:
    """Honor the global --no-color flag and the NO_COLOR env var."""
    if os.environ.get("NO_COLOR"):
        return False
    if ctx is not None and ctx.obj:
        return not bool(ctx.obj.get("no_color"))
    return True


def _echo(text: str, *, color: bool, fg: str | None = None) -> None:
    if color and fg:
        typer.echo(typer.style(text, fg=fg))
    else:
        typer.echo(text)


def _markers(project: Project) -> list[str]:
    """Ecosystem marker files + Dockerfile + flow directories, in scan order."""
    seen: list[str] = []
    for eco in project.ecosystems:
        seen.append(eco.marker.name)
    if project.dockerfile:
        seen.append("Dockerfile")
    for flow in project.flows:
        parent = flow.parent
        if parent != project.root:
            label = f"{parent.relative_to(project.root)}"
            if label not in seen:
                seen.append(label)
    return seen


def _flow_validity(path: Path) -> tuple[str, int | None, int | None]:
    """Return (status, n_errors, n_warnings) for one flow.

    Status is "ok" when validation (upto=2) found no errors, "bad" when it
    did, and "pending" when the pipeline is not built yet (Dev D's layers are
    stubs on this branch). The command must keep working while a teammate's
    seam is mid-build — a broken `yeet scan` is the one thing the Day-1 target
    forbids.
    """
    try:
        bag, _ = validate_file(path, upto=2)
    except NotImplementedError:
        return "pending", None, None
    errors = len(bag.errors)
    warnings = len(bag.warnings)
    return ("bad" if errors else "ok"), errors, warnings


def scan(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Directory to analyse.")] = Path(),
) -> None:
    """What is this project, and what flows does it have?

    Pipeline stages 1 + 2 + 3 (validation layers 0-2 only, for speed).
    Zero flows found is NOT an error — print the fingerprint and suggest
    `yeet init --auto`. That is what makes "point it at any repo" true.
    """
    color = _color_enabled(ctx)
    project = analyze(path)

    _echo(f"📦 project: {project.root}", color=color, fg=typer.colors.BRIGHT_WHITE)
    if project.is_git:
        branch = project.branch or "detached"
        _echo(f"   git:     {branch}", color=color, fg=typer.colors.CYAN)
    else:
        _echo("   git:     not a repo", color=color, fg=typer.colors.CYAN)
    _echo(f"   stack:   {project.stack}", color=color)
    _echo(f"   markers: {', '.join(_markers(project)) or '— none —'}", color=color)
    if project.truncated:
        _echo(
            "   ⚠ discovery hit the file cap — this report may be incomplete.",
            color=color,
            fg=typer.colors.YELLOW,
        )

    if not project.flows:
        _echo("", color=color)
        _echo("no flows found in this project.", color=color, fg=typer.colors.YELLOW)
        _echo(
            "run `yeet init --auto` to generate one for the stack above.",
            color=color,
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(0)

    _echo("", color=color)
    _echo(f"🔎 flows found: {len(project.flows)}", color=color, fg=typer.colors.BRIGHT_WHITE)
    for flow in project.flows:
        rel = flow.relative_to(project.root)
        status, n_errors, n_warnings = _flow_validity(flow)
        if status == "pending":
            _echo(
                f"   {_SKIP} {rel}      (validation not built yet)",
                color=color,
                fg=typer.colors.YELLOW,
            )
        elif status == "bad":
            _echo(
                f"   {_BAD} {rel}  {n_errors} errors, {n_warnings} warnings → run `yeet check`",
                color=color,
                fg=typer.colors.RED,
            )
        else:
            _echo(f"   {_OK} {rel}      valid", color=color, fg=typer.colors.GREEN)

    if project.foreign_ci:
        _echo("", color=color)
        _echo("🔎 foreign CI detected (not supported):", color=color, fg=typer.colors.BRIGHT_WHITE)
        for f in project.foreign_ci:
            _echo(f"   {_SKIP} {f.relative_to(project.root)}", color=color, fg=typer.colors.YELLOW)

    if project.dockerfile:
        _echo("", color=color)
        _echo(
            f"💡 {project.dockerfile.name} present → jobs without `cooked_on` will build it",
            color=color,
            fg=typer.colors.GREEN,
        )
