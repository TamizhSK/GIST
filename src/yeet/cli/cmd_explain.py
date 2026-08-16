"""yeet explain YEET-E203 — print the docs for one diagnostic code.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from yeet.core import codes
from yeet.core.resources import packaged_text

#: The repo's copy, for a dev checkout where it may be newer than the build.
_CHECKOUT_DOC = Path(__file__).resolve().parents[3] / "docs" / "rules.md"


def _rules_doc() -> str | None:
    """`rules.md`, from the checkout or from the wheel.

    It ships inside the package now. Before that this command reached
    `parents[3]/docs/`, which is the repo root from a checkout and the wrong
    directory entirely from site-packages — so every installed user got the
    two-line summary and a pointer to `make rules`, a command they had no
    Makefile for.
    """
    if _CHECKOUT_DOC.is_file():
        try:
            return _CHECKOUT_DOC.read_text(encoding="utf-8")
        except OSError:
            pass
    return packaged_text("rules.md")


def _section(code: str) -> str | None:
    """The `### \\`YEET-E301\\` — ...` block, up to the next rule heading."""
    doc = _rules_doc()
    if doc is None:
        return None
    lines = doc.splitlines()

    heading = f"### `{code}`"
    out: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith(heading):
            collecting = True
            out.append(line)
            continue
        if collecting:
            if line.startswith("### ") or line.startswith("## "):
                break
            out.append(line)

    body = "\n".join(out).strip()
    return body or None


def explain(
    code: Annotated[str, typer.Argument(help="A diagnostic code, e.g. YEET-E301.")],
) -> None:
    """Print that code's section of docs/rules.md."""
    clean_code = code.strip().upper()
    if not clean_code.startswith("YEET-"):
        clean_code = f"YEET-{clean_code}"

    try:
        rule = codes.get(clean_code)
    except KeyError:
        typer.secho(f"Unknown diagnostic code: {code}", fg=typer.colors.RED, err=True)
        typer.secho("See docs/rules.md for every code.", fg=typer.colors.YELLOW, err=True)
        sys.exit(1)

    section = _section(rule.code)
    if section:
        typer.echo(section)
        return

    # Only reachable if the doc did not ship. Say the same things from the
    # registry, which is where that document is generated from anyway.
    typer.echo(f"{rule.code} - {rule.title}")
    typer.echo("")
    typer.echo(f"  Default severity: {rule.default_severity.value}")
    typer.echo(f"  Pipeline layer:   {rule.layer}")
