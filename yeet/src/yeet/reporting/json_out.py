"""JSON diagnostic formatter.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import json
from typing import Any

from yeet.core.diagnostics import DiagnosticBag


def to_json(bag: DiagnosticBag) -> str:
    """Dump the Diagnostic list to a JSON string."""
    items: list[dict[str, Any]] = []
    for diag in bag.sorted():
        item: dict[str, Any] = {
            "code": diag.code,
            "severity": diag.severity.value,
            "message": diag.message,
            "file": str(diag.file) if diag.file else None,
            "line": (diag.pos.line + 1) if (diag.pos and diag.pos.is_known) else None,
            "col": (diag.pos.col + 1) if (diag.pos and diag.pos.is_known) else None,
            "help": diag.help,
            "note": diag.note,
            "url": diag.url,
        }
        items.append(item)

    return json.dumps({"diagnostics": items}, indent=2)
