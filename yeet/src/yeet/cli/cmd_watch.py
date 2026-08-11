"""yeet watch — daemon: watch for new/changed projects and dispatch runs.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.reporting.render import render_diagnostics
from yeet.triggers.watcher import watch_directory
from yeet.validation.pipeline import validate_file


def watch(
    path: Annotated[Path, typer.Argument(help="Directory to watch.")] = Path(),
) -> None:
    """Debounce 500ms, hold a per-project lock, ignore .git/node_modules/.yeet/tmp.

    A broken workflow file logs and waits. It must never crash the daemon.
    """
    target = path if path.exists() else Path.cwd()

    def on_change(file_path: Path) -> None:
        print(f"\n[watch] File changed: {file_path}")
        bag, _ = validate_file(file_path, upto=4)
        if bag.items:
            output = render_diagnostics(bag)
            print(output)
        else:
            print("✔ Workflow validation clean!")

    watch_directory(target, on_change)
