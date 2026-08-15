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

#: `src/yeet/cli/cmd_explain.py` -> the repo's `docs/rules.md`.
_RULES_DOC = Path(__file__).resolve().parents[3] / "docs" / "rules.md"


def _section(code: str) -> str | None:
    """The `### \\`YEET-E301\\` — ...` block, up to the next rule heading.

    Returns None when the doc is not on disk — an installed wheel ships the
    package and not the `docs/` tree — so the summary below is the fallback
    rather than an error.
    """
    if not _RULES_DOC.is_file():
        return None
    try:
        lines = _RULES_DOC.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

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

    # `docs/rules.md` is not installed alongside the package; say the same
    # things from the registry, which is where that document is generated from.
    typer.echo(f"{rule.code} - {rule.title}")
    typer.echo("")
    typer.echo(f"  Default severity: {rule.default_severity.value}")
    typer.echo(f"  Pipeline layer:   {rule.layer}")
    typer.echo("")
    typer.echo("Full docs: docs/rules.md (run `make rules` to regenerate).")
