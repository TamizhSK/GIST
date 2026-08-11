"""yeet secrets — store a secret locally.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

import typer

from yeet.secrets import store

secrets_app = typer.Typer(no_args_is_help=True, help="Local secret store.")


@secrets_app.command("set")
def set_(key: str = typer.Argument(..., help="Secret name.")) -> None:
    """Prompt for the value — never take it as an argv argument, shell history is forever."""
    val = typer.prompt(f"Enter secret value for {key}", hide_input=True)
    if not val:
        print("Empty value ignored.")
        return
    store.save_secret(Path.cwd(), key, val)
    print(f"Secret '{key}' stored.")


@secrets_app.command("list")
def list_() -> None:
    """Names only. Never print a value."""
    keys = store.list_secrets(Path.cwd())
    if not keys:
        print("No secrets stored in .yeet/.secrets")
        return
    print("Stored secrets:")
    for k in keys:
        print(f"  • {k}")


@secrets_app.command("rm")
def rm(key: str = typer.Argument(..., help="Secret name.")) -> None:
    deleted = store.remove_secret(Path.cwd(), key)
    if deleted:
        print(f"Secret '{key}' removed.")
    else:
        print(f"Secret '{key}' not found.")
