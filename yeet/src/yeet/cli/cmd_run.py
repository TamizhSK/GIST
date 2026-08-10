"""yeet run — the whole pipeline. Validates first; refuses on any error.

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo


def run(
    flow: Annotated[str | None, typer.Argument(help="Flow name. Default: all discovered.")] = None,
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    job: Annotated[str | None, typer.Option("--job", help="Run one job only.")] = None,
    event: Annotated[str, typer.Option("--event", help="Simulate a trigger.")] = "push",
    jobs: Annotated[int | None, typer.Option("--jobs", help="Max parallel jobs.")] = None,
    secret: Annotated[
        list[str] | None, typer.Option("--secret", help="K=V, highest precedence.")
    ] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
) -> None:
    """Analyze -> validate -> plan -> execute -> report.

    Layers 0-3 run and HARD STOP on any error before a container is created
    (exit 2). Layer 4 runs and prints but never blocks. That gate is the whole
    reason this tool is safe to point at a repo you did not write.
    """
    todo("run", "Dev C")
