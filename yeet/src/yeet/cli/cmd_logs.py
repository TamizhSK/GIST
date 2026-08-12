"""yeet logs — replay a past run from its JSONL.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.reporting.console import RunConsole
from yeet.storage.runs import replay


def logs(
    run_id: Annotated[str | None, typer.Argument(help="Run id. Default: the last run.")] = None,
) -> None:
    """Replays .yeet/runs/<run-id>/ through the same renderer a live run uses.

    Which means the log format is exercised every time anyone uses this — that
    is why it is worth building early rather than at the end.
    """
    root = Path.cwd()
    console = RunConsole()

    events = list(replay(root, run_id=run_id))
    if not events:
        target_name = run_id or "latest"
        typer.echo(f"No run logs found for '{target_name}'.")
        return

    typer.echo(f"--- Replaying log for run: {run_id or 'latest'} ---")
    for event in events:
        console.emit(event)
