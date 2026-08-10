"""yeet check — the full 5 layers. --strict, --format json|sarif.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def check(
    path: Annotated[Path, typer.Argument(help="File or directory to validate.")] = Path(),
    strict: Annotated[bool, typer.Option("--strict", help="Warnings become blocking.")] = False,
    format_: Annotated[str, typer.Option("--format", help="pretty | json | sarif")] = "pretty",
) -> None:
    """Is the .yml written correctly? Exit 0 clean, 2 on errors.

    The key deliverable: this must be evaluable without Docker installed.
    """
    todo("check", "Dev D")
