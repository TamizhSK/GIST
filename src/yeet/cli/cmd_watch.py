"""yeet watch — daemon: revalidate a flow the moment it is saved.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import EXIT_BAD_WORKFLOW, color_enabled
from yeet.reporting.render import render_diagnostics
from yeet.reporting.theme import SYMBOL_PASS
from yeet.triggers.watcher import DEBOUNCE_MS, LockHeld
from yeet.triggers.watcher import watch as watch_paths
from yeet.validation.pipeline import validate_file


def watch(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Directory to watch.")] = Path(),
    strict: Annotated[bool, typer.Option("--strict", help="Warnings count as failures.")] = False,
) -> None:
    """Debounce 500ms, hold a per-project lock, ignore the dirs a run writes to.

    A broken workflow file prints its diagnostics and the daemon keeps waiting.
    It must never crash — you leave this running in a second terminal all day.
    """
    target = (path if path.exists() else Path.cwd()).resolve()
    color = color_enabled(ctx)

    def on_change(file_path: Path) -> None:
        try:
            rel: Path | str = file_path.relative_to(target)
        except ValueError:
            rel = file_path
        typer.secho(f"\n[watch] {rel}", fg=typer.colors.CYAN if color else None)

        bag, _ = validate_file(file_path, strict=strict, upto=4)
        if len(bag):
            typer.echo(render_diagnostics(bag, color=color))
        if bag.exit_code(strict=strict) == 0:
            typer.secho(f"{SYMBOL_PASS} clean", fg=typer.colors.GREEN if color else None)

    def on_error(exc: Exception) -> None:
        # The daemon survives; the user still hears about it.
        typer.secho(f"[watch] {exc!r}", fg=typer.colors.RED if color else None, err=True)

    typer.secho(
        f"watching {target} (debounce {DEBOUNCE_MS}ms) — Ctrl-C to stop",
        fg=typer.colors.BRIGHT_WHITE if color else None,
    )
    try:
        watch_paths([target], on_change, on_error=on_error)
    except LockHeld as exc:
        typer.secho(str(exc), fg=typer.colors.RED if color else None, err=True)
        raise typer.Exit(EXIT_BAD_WORKFLOW) from exc
    typer.echo("\nstopped.")
