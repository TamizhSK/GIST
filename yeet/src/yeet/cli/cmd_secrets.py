"""yeet secrets — store a secret locally (encrypted).

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import typer

from yeet.cli import todo

secrets_app = typer.Typer(no_args_is_help=True, help="Local encrypted secret store.")


@secrets_app.command("set")
def set_(key: str = typer.Argument(..., help="Secret name.")) -> None:
    """Prompt for the value — never take it as an argv argument, shell history
    is forever."""
    todo("secrets set", "Dev D")


@secrets_app.command("list")
def list_() -> None:
    """Names only. Never print a value."""
    todo("secrets list", "Dev D")


@secrets_app.command("rm")
def rm(key: str = typer.Argument(..., help="Secret name.")) -> None:
    todo("secrets rm", "Dev D")
