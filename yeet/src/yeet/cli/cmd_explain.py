"""yeet explain YEET-E203 — print the docs for one diagnostic code.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from typing import Annotated

import typer

from yeet.cli import todo


def explain(
    code: Annotated[str, typer.Argument(help="A diagnostic code, e.g. YEET-E301.")],
) -> None:
    """Print that code's section of docs/rules.md."""
    todo("explain", "Dev D")
