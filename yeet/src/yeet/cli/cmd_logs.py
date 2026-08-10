"""yeet logs — replay a past run from its JSONL.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from typing import Annotated

import typer

from yeet.cli import todo


def logs(
    run_id: Annotated[str | None, typer.Argument(help="Run id. Default: the last run.")] = None,
) -> None:
    """Replays .yeet/runs/<run-id>/ through the same renderer a live run uses.

    Which means the log format is exercised every time anyone uses this — that
    is why it is worth building early rather than at the end.
    """
    todo("logs", "Dev D")
