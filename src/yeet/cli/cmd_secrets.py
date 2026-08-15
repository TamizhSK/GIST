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

from yeet.reporting.theme import SYMBOL_BULLET, SYMBOL_FROM, SYMBOL_WARN
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
            f"{SYMBOL_WARN} .yeet/.secrets is in the old PLAINTEXT format. "
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
        typer.echo(f"  {SYMBOL_BULLET} {key}")


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


@secrets_app.command("import")
def import_(
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    from_env: Annotated[
        bool,
        typer.Option("--from-env/--no-from-env", help="Take values from the current shell."),
    ] = True,
    write: Annotated[
        bool, typer.Option("--write/--dry-run", help="Write .env, or just report.")
    ] = True,
) -> None:
    """Collect the secrets and variables this project's workflows need into `.env`.

    Point yeet at a repo you just cloned and it can tell you exactly which
    `${{ secrets.X }}` and `${{ vars.Y }}` its workflows read — that list is in
    the workflow files, and nowhere else, so it is the one thing a new
    contributor cannot guess. Every name found is written to `.env`, filled in
    from your current environment where a variable of that name is already
    exported (`--no-from-env` to skip that) and left blank otherwise.

    Values already in `.env` are never overwritten: this runs safely a second
    time after someone adds a workflow, and it will not clobber a token you
    pasted in by hand. `.env` is in the generated `.gitignore` — check that
    before committing anything.
    """
    import os

    from yeet.analyzer.project import analyze
    from yeet.validation.layer3_semantic import referenced_names
    from yeet.validation.pipeline import validate_file

    root = path.resolve()
    project = analyze(root)
    if not project.flows:
        typer.secho("No flows found. Try `yeet init --auto`.", fg=typer.colors.YELLOW)
        raise typer.Exit(0)

    wanted: dict[str, str] = {}  # name -> "secret" | "variable"
    unreadable: list[Path] = []
    for flow in project.flows:
        _, workflow = validate_file(flow, upto=3)
        if workflow is None:
            unreadable.append(flow)
            continue
        for name in sorted(referenced_names(workflow, "secrets")):
            wanted[name] = "secret"
        for name in sorted(referenced_names(workflow, "vars")):
            wanted.setdefault(name, "variable")

    for flow in unreadable:
        typer.secho(
            f"  ~ {flow.relative_to(root)} does not parse — skipped. Run `yeet check`.",
            fg=typer.colors.YELLOW,
        )

    # GitHub injects this one; a workflow reads it without anyone setting it,
    # so asking the user to supply it would be asking for something that does
    # not exist locally.
    wanted.pop("GITHUB_TOKEN", None)

    if not wanted:
        typer.secho("No secrets or variables referenced by these workflows.", fg=typer.colors.GREEN)
        raise typer.Exit(0)

    env_path = root / ".env"
    existing = store.read_dotenv(root)

    added: list[str] = []
    filled: list[str] = []
    lines: list[str] = []
    for name, kind in sorted(wanted.items()):
        if name in existing:
            continue
        value = os.environ.get(name, "") if from_env else ""
        lines.append(f"{name}={value}")
        added.append(name)
        if value:
            filled.append(name)
        typer.echo(
            f"  {'+' if not value else '='} {name}"
            f"{typer.style(f'  ({kind})', fg=typer.colors.BRIGHT_BLACK)}"
            + (
                typer.style(f"  {SYMBOL_FROM} from your environment", fg=typer.colors.GREEN)
                if value
                else ""
            )
        )

    for name in sorted(wanted):
        if name in existing:
            dot = typer.style("-", fg=typer.colors.BRIGHT_BLACK)
            typer.echo(f"  {dot} {name}  already in .env")

    if not added:
        typer.secho("\n.env already has everything these workflows need.", fg=typer.colors.GREEN)
        raise typer.Exit(0)

    if not write:
        typer.secho(
            f"\n--dry-run: would add {len(added)} entr(y/ies) to .env", fg=typer.colors.YELLOW
        )
        raise typer.Exit(0)

    header = "" if env_path.exists() else "# Written by `yeet secrets import`. Do not commit.\n"
    with env_path.open("a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write("\n".join(lines) + "\n")

    blank = len(added) - len(filled)
    typer.secho(f"\nwrote {len(added)} entr(y/ies) to {env_path}", fg=typer.colors.GREEN)
    if blank:
        typer.secho(
            f"{blank} still need a value — edit .env, or `yeet secrets set <NAME>` "
            "to keep it encrypted instead.",
            fg=typer.colors.YELLOW,
        )
