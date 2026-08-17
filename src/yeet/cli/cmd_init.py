"""yeet init — scaffold a flow (--auto generates one from the detected stack).

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md

Writes:
  .yeet/flows/main.yml          the flow (dialect)
  .yeet/actions/checkout/       the zero-dependency checkout action (A19)
  .gitignore                    appends the runtime-state block

`--auto` reads the fingerprint (markers.py) and generates one job per detected
ecosystem. Without `--auto` you get a minimal valid flow to edit. Overwriting a
flow you already have is a bigger decision than scaffolding a new one, so init
refuses when .yeet/flows/main.yml already exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.analyzer.project import analyze
from yeet.templates import workflows

CHECKOUT_REL = Path(".yeet") / "actions" / "checkout" / "action.yml"


def init(
    path: Annotated[Path, typer.Argument(help="Project to scaffold into.")] = Path(),
    auto: Annotated[bool, typer.Option("--auto", help="Generate from the fingerprint.")] = False,
) -> None:
    """Write .yeet/flows/main.yml, plus the .gitignore entries for runtime state."""
    target = path.expanduser().resolve()
    if not target.is_dir():
        typer.secho(f"no such directory: {target}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    project = analyze(target)
    name = project.root.name

    flow_path = project.root / ".yeet" / "flows" / "main.yml"
    if flow_path.exists():
        rel = flow_path.relative_to(project.root)
        typer.secho(f"a flow already exists at {rel}", fg=typer.colors.RED, err=True)
        typer.secho("edit it, or delete it and re-run `yeet init`", fg=typer.colors.YELLOW)
        raise typer.Exit(2)

    if auto:
        flow = workflows.auto_flow(
            name, project.ecosystems, dockerfile=project.dockerfile is not None
        )
    else:
        flow = workflows.default_flow(name)

    flow_path.parent.mkdir(parents=True, exist_ok=True)
    flow_path.write_text(flow, encoding="utf-8")

    checkout_path = project.root / CHECKOUT_REL
    checkout_path.parent.mkdir(parents=True, exist_ok=True)
    checkout_path.write_text(workflows.render_checkout_action(), encoding="utf-8")

    _append_gitignore(project.root)

    typer.echo(f"wrote {flow_path.relative_to(project.root)}")
    typer.echo(f"wrote {CHECKOUT_REL.as_posix()}")
    if auto and project.ecosystems:
        stack = " · ".join(e.name for e in project.ecosystems)
        typer.echo(f"generated for: {stack}")
    typer.echo("next: `yeet check .` then `yeet run .`")


def _append_gitignore(root: Path) -> None:
    """Append the runtime-state block only if it isn't there already."""
    ignore = root / ".gitignore"
    block = workflows.gitignore_entries()
    if ignore.is_file():
        try:
            existing = ignore.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    else:
        existing = ""
    if ".yeet/tmp/" in existing:
        return
    with ignore.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(block)
