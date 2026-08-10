"""yeet hooks install — write git hooks into .git/hooks.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import todo

hooks_app = typer.Typer(no_args_is_help=True, help="Git hook integration.")


@hooks_app.command("install")
def install(
    path: Annotated[Path, typer.Argument(help="Repository to install into.")] = Path(),
    blocking: Annotated[bool, typer.Option("--blocking", help="Fail the push on red.")] = False,
) -> None:
    """post-commit + pre-push shims, chmod 0o755, shebang-sh so Windows works."""
    todo("hooks install", "Dev D")


@hooks_app.command("uninstall")
def uninstall(
    path: Annotated[Path, typer.Argument(help="Repository to clean.")] = Path(),
) -> None:
    """Remove only the hooks we wrote. Never clobber a hook we did not create."""
    todo("hooks uninstall", "Dev D")
