"""Cross-reference checks over the IR: needs, cycles, step ids, contexts, matrix vars.

Owner: Dev B
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def check(wf: "Workflow") -> DiagnosticBag:
    """E301 E302 E303 E305-E317. Reuses planner.graph for cycle detection."""
    raise NotImplementedError
