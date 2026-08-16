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

from yeet.analyzer.discover import discover_flows
from yeet.core.diagnostics import DiagnosticBag
from yeet.reporting.json_out import to_json
from yeet.reporting.render import render_diagnostics
from yeet.reporting.sarif import to_sarif
from yeet.reporting.theme import SYMBOL_FAIL, SYMBOL_PASS
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
        # `analyzer.discover`, the same walk `yeet scan` uses. This command had
        # its own two-line version that globbed `*.yml` in `.yeet/flows` and
        # `.github/workflows` only — so a project using `.yaml`, or a bare
        # `workflows/` at the root, got "No workflow files found" and exit 0.
        # `scan` listed the files; `check` reported nothing wrong with files it
        # had never opened. A false green is the one result this tool must
        # never produce.
        flow_candidates, foreign = discover_flows(target)
        if not flow_candidates:
            typer.echo(f"No workflow files found in {target}", err=True)
            for other in foreign:
                typer.echo(f"  found {other.name}, which yeet does not support", err=True)
            typer.echo("Run `yeet init --auto` to generate one.", err=True)
            sys.exit(0)
    else:
        flow_candidates = [target]

    combined_bag = DiagnosticBag()
    for flow in flow_candidates:
        bag, _ = validate_file(flow, strict=strict, upto=4)
        combined_bag.extend(bag)

    if format_ == "json":
        # Always valid JSON, including when there is nothing to say. A consumer
        # parsing empty output fails on the clean case, which is the common one.
        typer.echo(to_json(combined_bag))
    elif format_ == "sarif":
        typer.echo(to_sarif(combined_bag))
    else:
        output = render_diagnostics(combined_bag)
        if output.strip():
            typer.echo(output)
        typer.echo(_summary(flow_candidates, combined_bag, target))

    exit_code = combined_bag.exit_code(strict=strict)
    sys.exit(exit_code)


def _summary(flows: list[Path], bag: DiagnosticBag, target: Path) -> str:
    """One line naming what was checked and what was found.

    A clean run used to print nothing at all, which is indistinguishable from a
    run that found no files — and those had very different meanings and the
    same exit code.
    """
    errors, warnings = len(bag.errors), len(bag.warnings)
    mark = SYMBOL_FAIL if errors else SYMBOL_PASS
    counts = "clean" if not len(bag) else f"{errors} error(s), {warnings} warning(s)"
    if not target.is_dir():
        return f"{mark} {flows[0]}: {counts}"
    what = "flow" if len(flows) == 1 else "flows"
    return f"{mark} {len(flows)} {what} checked: {counts}"
