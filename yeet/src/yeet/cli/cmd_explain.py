"""yeet explain YEET-E203 — print the docs for one diagnostic code.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from yeet.core import codes


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
        print(f"Unknown diagnostic code: {code}")
        print("Run `yeet check` to see available rule codes.")
        sys.exit(1)

    print(f"Rule Code:        {rule.code}")
    print(f"Title:            {rule.title}")
    print(f"Default Severity: {rule.default_severity.value}")
    print(f"Pipeline Layer:   {rule.layer}")
    print(f"Documentation:    yeet/docs/rules.md#{rule.code.lower()}")
