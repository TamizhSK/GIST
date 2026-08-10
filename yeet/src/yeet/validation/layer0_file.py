"""File & encoding: empty, non-UTF8, BOM, TAB indentation, CRLF, absurd size.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def check(path: Path) -> DiagnosticBag:
    raise NotImplementedError
