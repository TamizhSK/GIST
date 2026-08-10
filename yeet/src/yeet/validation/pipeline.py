"""Runs layers 0-4 in order. Stops BETWEEN layers on error, not within one.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def validate_file(path: Path, *, strict: bool = False, upto: int = 4) -> DiagnosticBag:
    """layer0 -> layer1 -> layer2 -> layer3 -> layer4. Return everything found."""
    raise NotImplementedError
