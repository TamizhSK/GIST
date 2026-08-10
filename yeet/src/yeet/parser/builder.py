"""Normalized dict tree -> IR dataclasses. Attaches a Position to every node.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Workflow


def build_workflow(data: Any, source: Path, bag: DiagnosticBag) -> Workflow | None:
    """Emits E204/E205 as it constructs each Step.

    Every node gets its `pos=` from `data.lc.value(key)` AS IT IS BUILT, not in
    a second pass. This is the one decision that cannot be walked back — see
    architecture.md 3.10 and risk #4 in plan.md.
    """
    raise NotImplementedError
