"""Runs layers 0-4 in order. Stops BETWEEN layers on error, not within one.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Workflow


def validate_file(
    path: Path, *, strict: bool = False, upto: int = 4
) -> tuple[DiagnosticBag, Workflow | None]:
    """layer0 -> layer1 -> layer2 -> layer3 -> layer4. Return everything found.

    Returns the built Workflow alongside the bag so `cmd_run` can validate and
    then plan without parsing the file a second time. It is None whenever a
    layer below 3 produced an error and parsing stopped.

    Stop BETWEEN layers, never within one: there is no point schema-checking a
    file that is not valid YAML, but a user who fixes one broken `needs:` per
    run will hate this tool.

    `upto` is what makes every command a prefix of the same pipeline:
      scan -> upto=2   check -> upto=4   run -> upto=3 (+ layer 4, non-blocking)
    """
    raise NotImplementedError
