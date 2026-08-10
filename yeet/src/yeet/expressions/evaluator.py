"""Walk the AST. Replicate GitHub's loose equality ('1' == 1 is true).

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""
from __future__ import annotations

def evaluate(node: "Node", ctx: "Contexts") -> object:
    raise NotImplementedError
