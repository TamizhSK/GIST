"""yeet secrets — store a secret locally, encrypted.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md

The store is passphrase-encrypted (see `secrets/store.py`). This file owns the
only interactive part: prompting for that passphrase, and offering to remember
it in the OS keyring so `yeet run` does not need `$YEET_PASSPHRASE` set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.secrets import store
from yeet.secrets.store import SecretsError

secrets_app = typer.Typer(no_args_is_help=True, help="Local secret store.")

_REMEMBER_HINT = (
    "Tip: `pip install keyring` and yeet will remember this passphrase, "
    f"or export ${store.PASSPHRASE_ENV}."
)


def _passphrase(*, confirm: bool) -> str:
    """The passphrase, prompting only if we cannot find one already."""
    existing = store.resolve_passphrase()
    if existing:
        return existing

    passphrase = str(
        typer.prompt(
            "Passphrase for .yeet/.secrets",
            hide_input=True,
            confirmation_prompt=confirm,
        )
    )
    if not passphrase:
        typer.secho("A passphrase is required.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if store.keyring_set(passphrase):
        typer.secho("Saved the passphrase to your OS keyring.", fg=typer.colors.GREEN)
    else:
        typer.secho(_REMEMBER_HINT, fg=typer.colors.YELLOW, err=True)
    return passphrase


def _warn_if_legacy(root: Path) -> None:
    if store.is_legacy_plaintext(root):
        typer.secho(
            "⚠ .yeet/.secrets is in the old PLAINTEXT format. "
            "Run `yeet secrets set <NAME>` on any secret to re-encrypt the whole store.",
            fg=typer.colors.YELLOW,
            err=True,
        )


@secrets_app.command("set")
def set_(key: Annotated[str, typer.Argument(help="Secret name.")]) -> None:
    """Prompt for the value — never take it as an argv argument, shell history is forever."""
    root = Path.cwd()
    _warn_if_legacy(root)

    value = typer.prompt(f"Enter secret value for {key}", hide_input=True)
    if not value:
        typer.secho("Empty value ignored.", fg=typer.colors.YELLOW, err=True)
        return

    passphrase = _passphrase(confirm=not (root / store.SECRETS_FILE).exists())
    try:
        store.save_secret(root, key, value, passphrase=passphrase)
    except SecretsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Secret '{key}' stored (encrypted).")


@secrets_app.command("list")
def list_() -> None:
    """Names only. Never print a value."""
    root = Path.cwd()
    if not (root / store.SECRETS_FILE).exists():
        typer.echo("No secrets stored in .yeet/.secrets")
        return
    _warn_if_legacy(root)

    try:
        keys = store.list_secrets(root, passphrase=_passphrase(confirm=False))
    except SecretsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    if not keys:
        typer.echo("No secrets stored in .yeet/.secrets")
        return
    typer.echo("Stored secrets:")
    for key in keys:
        typer.echo(f"  • {key}")


@secrets_app.command("rm")
def rm(key: Annotated[str, typer.Argument(help="Secret name.")]) -> None:
    """Remove one secret."""
    root = Path.cwd()
    try:
        deleted = store.remove_secret(root, key, passphrase=_passphrase(confirm=False))
    except SecretsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    if not deleted:
        typer.secho(f"Secret '{key}' not found.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(1)
    typer.echo(f"Secret '{key}' removed.")
