"""yeet watch — daemon: watch for new/changed projects and dispatch runs.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def watch(
    path: Annotated[Path, typer.Argument(help="Directory to watch.")] = Path(),
) -> None:
    """Debounce 500ms, hold a per-project lock, ignore .git/node_modules/.yeet/tmp.

    A broken workflow file logs and waits. It must never crash the daemon.
    """
    todo("watch", "Dev D")
