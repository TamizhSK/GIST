"""yeet check — the full 5 layers. --strict, --format json|sarif.

Owner: Dev D
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from yeet.reporting.json_out import to_json
from yeet.reporting.render import render_diagnostics
from yeet.reporting.sarif import to_sarif
from yeet.validation.pipeline import validate_file


def check(
    path: Annotated[Path, typer.Argument(help="File or directory to validate.")] = Path(),
    strict: Annotated[bool, typer.Option("--strict", help="Warnings become blocking.")] = False,
    format_: Annotated[str, typer.Option("--format", help="pretty | json | sarif")] = "pretty",
) -> None:
    """Is the .yml written correctly? Exit 0 clean, 2 on errors.

    The key deliverable: this must be evaluable without Docker installed.
    """
    target = path if path.exists() else Path.cwd()

    if target.is_dir():
        # Look for workflow files in .yeet/flows or .github/workflows or yeet.yml
        flow_candidates = list((target / ".yeet" / "flows").glob("*.yml")) + list(
            (target / ".github" / "workflows").glob("*.yml")
        )
        if not flow_candidates and (target / "yeet.yml").exists():
            flow_candidates = [target / "yeet.yml"]
        if not flow_candidates:
            typer.echo(f"No workflow files found in {target}")
            sys.exit(0)
    else:
        flow_candidates = [target]

    from yeet.core.diagnostics import DiagnosticBag

    combined_bag = DiagnosticBag()
    for flow in flow_candidates:
        bag, _ = validate_file(flow, strict=strict, upto=4)
        combined_bag.extend(bag)

    if format_ == "json":
        output = to_json(combined_bag)
    elif format_ == "sarif":
        output = to_sarif(combined_bag)
    else:
        output = render_diagnostics(combined_bag)

    if output.strip():
        typer.echo(output)

    exit_code = combined_bag.exit_code(strict=strict)
    sys.exit(exit_code)
