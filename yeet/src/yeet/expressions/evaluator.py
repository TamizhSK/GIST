"""Walk the AST. Replicate GitHub's loose equality ('1' == 1 is true).

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from yeet.expressions.ast_nodes import Node
from yeet.expressions.contexts import Contexts


def evaluate(node: Node, ctx: Contexts) -> object:
    """NEVER eval(). Member access on a missing key returns None, not an error —
    GitHub's behaviour, and `${{ steps.absent.outputs.x }}` must not crash a run.

    Replicate the loose-equality coercion ('1' == 1, '' == 0) or document
    loudly that we don't. Silently differing is the one unacceptable option.
    """
    raise NotImplementedError
