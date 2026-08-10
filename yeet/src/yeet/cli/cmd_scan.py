"""yeet scan — analyse a project: type, flows found, health report.

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def scan(
    path: Annotated[Path, typer.Argument(help="Directory to analyse.")] = Path(),
) -> None:
    """What is this project, and what flows does it have?

    Pipeline stages 1 + 2 + 3 (validation layers 0-2 only, for speed).
    Zero flows found is NOT an error — print the fingerprint and suggest
    `yeet init --auto`. That is what makes "point it at any repo" true.
    """
    todo("scan", "Dev A")
