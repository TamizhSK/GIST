"""yeet init — scaffold a flow (--auto generates one from the detected stack).

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def init(
    path: Annotated[Path, typer.Argument(help="Project to scaffold into.")] = Path(),
    auto: Annotated[bool, typer.Option("--auto", help="Generate from the fingerprint.")] = False,
) -> None:
    """Write .yeet/flows/main.yml, plus the .gitignore entries for runtime state."""
    todo("init", "Dev A")
