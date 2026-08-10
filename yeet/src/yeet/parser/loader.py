"""ruamel.yaml round-trip load. Emits E101/E102/E103/W105. KEEPS line+col.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import DiagnosticBag


def load_with_positions(path: Path, bag: DiagnosticBag) -> Any | None:
    """YAML(typ='rt'); use .lc.key()/.lc.value() for every position.

    Returns None on E101/E103 — the caller must stop rather than schema-check
    a tree that never parsed. Subclass the constructor so duplicate keys RAISE
    (E102): PyYAML silently keeps the last one, and two `moves:` keys silently
    dropping half a workflow is a nightmare to debug.
    """
    raise NotImplementedError
