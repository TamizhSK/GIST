"""Pratt parser. NEVER eval(). Raises ExprSyntaxError with an offset.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from yeet.expressions.ast_nodes import Node


def parse(src: str) -> Node:
    """Parse the INSIDE of `${{ }}` (the braces are stripped by the caller).

    `if:` accepts a bare expression without the braces — GitHub permits it, so
    the same function serves both and the caller decides whether to strip.

    Raises ExprSyntaxError(offset, message). Never returns a partial tree: a
    half-parsed expression that evaluates to something plausible is worse than
    a clean E309.
    """
    raise NotImplementedError
