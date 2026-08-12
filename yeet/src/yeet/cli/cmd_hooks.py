"""yeet hooks install — write git hooks into .git/hooks.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.triggers import hooks

hooks_app = typer.Typer(no_args_is_help=True, help="Git hook integration.")


@hooks_app.command("install")
def install(
    path: Annotated[Path, typer.Argument(help="Repository to install into.")] = Path(),
    blocking: Annotated[bool, typer.Option("--blocking", help="Fail the push on red.")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Replace a hook yeet did not write.")
    ] = False,
) -> None:
    """post-commit + pre-push shims, chmod 0o755, shebang-sh so Windows works."""
    root = path if path.exists() else Path.cwd()
    try:
        installed = hooks.install(root, blocking=blocking, force=force)
    except Exception as exc:
        typer.secho(f"Failed to install hooks: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    typer.echo("Installed git hooks:")
    for h in installed:
        typer.echo(f"  • {h}")


@hooks_app.command("uninstall")
def uninstall(
    path: Annotated[Path, typer.Argument(help="Repository to clean.")] = Path(),
) -> None:
    """Remove only the hooks we wrote. Never clobber a hook we did not create."""
    root = path if path.exists() else Path.cwd()
    removed = hooks.uninstall(root)
    if not removed:
        typer.echo("No yeet git hooks found to uninstall.")
        return
    typer.echo("Removed yeet git hooks:")
    for h in removed:
        typer.echo(f"  • {h}")
