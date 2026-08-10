"""ruamel.yaml round-trip load. Emits E101/E102/E103/W105. KEEPS line+col.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def load_with_positions(path: Path, bag: DiagnosticBag) -> object | None:
    """YAML(typ='rt'); use .lc.key()/.lc.value() for every position."""
    raise NotImplementedError
