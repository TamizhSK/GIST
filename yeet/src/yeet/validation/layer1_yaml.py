"""YAML syntax + duplicate keys + the `on:`-is-True trap.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def check(path: Path) -> tuple[DiagnosticBag, object | None]:
    raise NotImplementedError
