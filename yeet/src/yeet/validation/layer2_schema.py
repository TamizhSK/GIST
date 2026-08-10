"""jsonschema against workflow.schema.json; best_match + readable JSON paths.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def check(data: object, path: Path) -> DiagnosticBag:
    raise NotImplementedError
