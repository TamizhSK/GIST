"""yeet graph — print the job DAG. 30 lines, great demo moment.

Owner: Dev B
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def graph(
    path: Annotated[Path, typer.Argument(help="Project directory.")] = Path(),
) -> None:
    """Pipeline stages 1-4. ASCII tree of jobs, waves and matrix legs."""
    todo("graph", "Dev B")
