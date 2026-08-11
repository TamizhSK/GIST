"""Pratt parser. NEVER eval(). Raises ExprSyntaxError with an offset.

Precedence follows GitHub's documented order (highest first):
    `[ ]` index · `.` member / `*` splat · `(` call
    `!` not
    `< <= > >=` comparison
    `== !=` equality
    `&&` and
    `||` or
`!` binds tighter than the comparisons, so `!a == b` is `(!a) == b`.

Never returns a partial tree: any trailing token after the top-level
expression is an error, because a half-parsed expression that evaluates to
something plausible is worse than a clean E309.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from yeet.expressions import lexer
from yeet.expressions.ast_nodes import (
    Binary,
    Call,
    ExprSyntaxError,
    Ident,
    Index,
    Literal,
    Member,
    Node,
    Splat,
    Unary,
)
from yeet.expressions.lexer import Token

# Operator token kinds and their left binding power. Higher binds tighter.
BINARY_BP: dict[str, int] = {
    lexer.OR: 1,
    lexer.AND: 2,
    lexer.EQ: 3,
    lexer.NEQ: 3,
    lexer.LT: 4,
    lexer.GT: 4,
    lexer.LTE: 4,
    lexer.GTE: 4,
}
NOT_BP = 5  # `!` — tighter than comparisons, looser than member access
POSTFIX_BP = 7  # `.` `[` `(` — the tightest bindings

_KEYWORDS = {"true": True, "false": False, "null": None}


def parse(src: str) -> Node:
    """Parse the INSIDE of `${{ }}` (the braces are stripped by the caller).

    `if:` accepts a bare expression without the braces — GitHub permits it, so
    the same function serves both and the caller decides whether to strip.

    Raises ExprSyntaxError(offset, message). Never returns a partial tree: a
    half-parsed expression that evaluates to something plausible is worse than
    a clean E309.
    """
    tokens = lexer.tokenize(src)
    if not tokens:
        raise ExprSyntaxError(0, "empty expression")
    parser = _Parser(tokens, len(src.encode("utf-8")))
    node = parser.expr(0)
    trailing = parser.peek()
    if trailing is not None:
        raise ExprSyntaxError(trailing.offset, "unexpected trailing tokens")
    return node


class _Parser:
    def __init__(self, tokens: list[Token], end_offset: int) -> None:
        self.tokens = tokens
        self.end_offset = end_offset
        self.pos = 0

    def peek(self) -> Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def next(self) -> Token:
        token = self.peek()
        if token is None:
            raise ExprSyntaxError(self.end_offset, "unexpected end of expression")
        self.pos += 1
        return token

    def expr(self, min_bp: int) -> Node:
        left = self.nud()
        while True:
            token = self.peek()
            if token is None:
                break
            if token.kind in BINARY_BP and BINARY_BP[token.kind] >= min_bp:
                left = self.binary(left, BINARY_BP[token.kind])
                continue
            if token.kind == lexer.DOT and min_bp <= POSTFIX_BP:
                left = self.member(left)
                continue
            if token.kind == lexer.LBRACKET and min_bp <= POSTFIX_BP:
                left = self.index(left)
                continue
            if token.kind == lexer.LPAREN and min_bp <= POSTFIX_BP:
                left = self.call(left)
                continue
            break
        return left

    def nud(self) -> Node:
        token = self.next()
        if token.kind == lexer.STRING:
            return Literal(value=token.value, offset=token.offset)
        if token.kind == lexer.NUMBER:
            return Literal(value=token.value, offset=token.offset)
        if token.kind == lexer.IDENT:
            lower = token.value.lower()
            if lower in _KEYWORDS:
                return Literal(value=_KEYWORDS[lower], offset=token.offset)
            return Ident(name=token.value, offset=token.offset)
        if token.kind == lexer.BANG:
            return Unary(op="!", operand=self.expr(NOT_BP), offset=token.offset)
        if token.kind == lexer.LPAREN:
            inner = self.expr(0)
            close = self.next()
            if close.kind != lexer.RPAREN:
                raise ExprSyntaxError(close.offset, "expected `)`")
            return inner
        raise ExprSyntaxError(token.offset, f"unexpected token `{token.kind}`")

    def binary(self, left: Node, bp: int) -> Node:
        op = self.next()
        right = self.expr(bp + 1)
        return Binary(op=op.kind, left=left, right=right, offset=op.offset)

    def member(self, left: Node) -> Node:
        dot = self.next()
        following = self.next()
        if following.kind == lexer.STAR:
            return Splat(target=left, offset=dot.offset)
        if following.kind == lexer.IDENT:
            return Member(target=left, name=following.value, offset=dot.offset)
        raise ExprSyntaxError(following.offset, "expected a property name after `.`")

    def index(self, left: Node) -> Node:
        open_bracket = self.next()
        key = self.expr(0)
        close = self.next()
        if close.kind != lexer.RBRACKET:
            raise ExprSyntaxError(close.offset, "expected `]`")
        return Index(target=left, index=key, offset=open_bracket.offset)

    def call(self, left: Node) -> Node:
        open_paren = self.next()
        if not isinstance(left, Ident):
            raise ExprSyntaxError(open_paren.offset, "function calls must be on a bare name")
        args: list[Node] = []
        if self._peek_kind() == lexer.RPAREN:
            self.next()
            return Call(name=left.name, args=tuple(args), offset=left.offset)
        args.append(self.expr(0))
        while self._peek_kind() == lexer.COMMA:
            self.next()
            args.append(self.expr(0))
        close = self.next()
        if close.kind != lexer.RPAREN:
            raise ExprSyntaxError(close.offset, "expected `)`")
        return Call(name=left.name, args=tuple(args), offset=left.offset)

    def _peek_kind(self) -> str | None:
        token = self.peek()
        if token is None:
            return None
        return token.kind
