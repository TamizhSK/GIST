"""Walk the AST. Never `eval()`. Member access on a missing key returns None,
not an error — GitHub's behaviour, and `${{ steps.absent.outputs.x }}` must not
crash a run.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from collections.abc import Mapping

from yeet.expressions import functions
from yeet.expressions._comparison import compare, loose_equal
from yeet.expressions.ast_nodes import (
    Binary,
    Call,
    Ident,
    Index,
    Literal,
    Member,
    Node,
    Splat,
    Unary,
)
from yeet.expressions.contexts import Contexts


def evaluate(node: Node | None, ctx: Contexts) -> object:
    """The entry point every caller uses. A missing child (`None`) evaluates to
    null — the parser never produces one, but the AST node types allow it, so
    the walker degrades instead of crashing. Raises ValueError on a node it
    does not know how to walk — a bug, not a user error."""
    if node is None:
        return None
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, Ident):
        return _context_value(node.name, ctx)
    if isinstance(node, Member):
        return _member(evaluate(node.target, ctx), node.name)
    if isinstance(node, Index):
        return _index(evaluate(node.target, ctx), evaluate(node.index, ctx))
    if isinstance(node, Splat):
        return _splat(evaluate(node.target, ctx))
    if isinstance(node, Unary):
        return not truthy(evaluate(node.operand, ctx))
    if isinstance(node, Binary):
        return _binary(node, ctx)
    if isinstance(node, Call):
        return functions.lookup(node.name)([evaluate(arg, ctx) for arg in node.args], ctx)
    raise ValueError(f"cannot evaluate node {type(node).__name__}")


def truthy(value: object) -> bool:
    """GitHub's falsy set is exactly `false`, `0`, `-0`, `""`, `''`, `null`.

    Note what is *not* in it: the string `"false"` is truthy, which surprises
    everyone exactly once, and then they stop putting booleans in env vars.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value != ""
    return True


def _context_value(name: str, ctx: Contexts) -> object:
    value = getattr(ctx, name, None)
    if value is None:
        return None
    return value


def _member(value: object, name: str) -> object:
    if value is None:
        return None
    if isinstance(value, Mapping):
        exact = value.get(name)
        if exact is not None:
            return exact
        # GitHub context access ignores case; exact match above wins so that
        # case-sensitive contexts (`env`, `secrets`) keep their contract.
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() == name.casefold():
                return item
        return None
    if isinstance(value, (list, tuple)):
        # `needs.*.result` maps the member over the splat array.
        return [_member(item, name) for item in value]
    return getattr(value, name, None)


def _index(value: object, key: object) -> object:
    if value is None or key is None:
        return None
    if isinstance(value, Mapping):
        return _member(value, key if isinstance(key, str) else str(key))
    if isinstance(key, int) and isinstance(value, (list, tuple)):
        return value[key] if -len(value) <= key < len(value) else None
    return None


def _splat(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, (list, tuple)):
        flattened: list[object] = []
        for item in value:
            if isinstance(item, (list, tuple)):
                flattened.extend(item)
            else:
                flattened.append(item)
        return flattened
    return [value]


def _binary(node: Binary, ctx: Contexts) -> object:
    op = node.op
    if op == "&&":
        left = evaluate(node.left, ctx)
        return evaluate(node.right, ctx) if truthy(left) else left
    if op == "||":
        left = evaluate(node.left, ctx)
        return left if truthy(left) else evaluate(node.right, ctx)
    if op == "==":
        return loose_equal(evaluate(node.left, ctx), evaluate(node.right, ctx))
    if op == "!=":
        return not loose_equal(evaluate(node.left, ctx), evaluate(node.right, ctx))
    if op in ("<", "<=", ">", ">="):
        return compare(op, evaluate(node.left, ctx), evaluate(node.right, ctx))
    raise ValueError(f"unknown binary operator {op!r}")
