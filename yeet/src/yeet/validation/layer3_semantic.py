"""Cross-reference checks over the IR: needs, cycles, step ids, contexts, matrix vars.

Owner: Dev B
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.graph import find_cycle
from yeet.core.ir import Workflow

__all__ = ["check", "find_cycle"]


def check(wf: Workflow) -> DiagnosticBag:
    """E301 E302 E303 E305-E317, W318-W319.

    E302 calls `core.graph.find_cycle` — the SAME function the scheduler uses.
    Do not write a second cycle walk; two copies drift and then the validator
    and the planner disagree about whether a workflow is runnable.

    (The guide says "planner.graph does double duty". It cannot: planner is
    tier 4, validation is tier 3, and importing upward is what lint-imports
    exists to stop. The algorithm therefore sits in core.graph and both sides
    adapt to it. See plan.md 3.5.)
    """
    raise NotImplementedError
