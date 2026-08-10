"""Normalized dict tree -> IR dataclasses. Attaches a Position to every node.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def build_workflow(data: object, source: Path, bag: DiagnosticBag) -> "Workflow | None":
    raise NotImplementedError
