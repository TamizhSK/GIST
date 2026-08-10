"""AST node dataclasses.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Node:
    """Base for every expression node. `offset` is the character index inside
    the expression source — E309 reports the offset *within* `${{ }}`, not the
    line of the whole file, so it survives being embedded anywhere."""

    offset: int = 0


@dataclass(frozen=True, slots=True)
class Literal(Node):
    value: Any = None


@dataclass(frozen=True, slots=True)
class Ident(Node):
    """A context name: `github`, `matrix`, `secrets`."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class Member(Node):
    """`a.b`"""

    target: Node | None = None
    name: str = ""


@dataclass(frozen=True, slots=True)
class Index(Node):
    """`a['b']` / `a[0]`"""

    target: Node | None = None
    index: Node | None = None


@dataclass(frozen=True, slots=True)
class Splat(Node):
    """`jobs.*.outputs` — the wildcard that returns a flattened list."""

    target: Node | None = None


@dataclass(frozen=True, slots=True)
class Unary(Node):
    op: str = "!"
    operand: Node | None = None


@dataclass(frozen=True, slots=True)
class Binary(Node):
    op: str = "=="
    left: Node | None = None
    right: Node | None = None


@dataclass(frozen=True, slots=True)
class Call(Node):
    name: str = ""
    args: tuple[Node, ...] = field(default_factory=tuple)


class ExprSyntaxError(Exception):
    """Raised by the parser. Carries the offset so E309 can point at it."""

    def __init__(self, offset: int, message: str) -> None:
        super().__init__(message)
        self.offset = offset
        self.message = message
