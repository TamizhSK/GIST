"""Tokenize the inside of `${{ }}`. Track offsets for E309.

Tokens carry the offset *inside* the expression source, so an error can point
at `{{ github.ref_naem }}` rather than at the workflow line — the expression
may be embedded in a `run:` block where line numbers are meaningless.

Offsets are byte offsets (a `len(s.encode("utf-8"))` walk), matching the plan's
"track byte offsets". For ASCII expressions they coincide with character
indices; that is what every expression in practice is.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yeet.expressions.ast_nodes import ExprSyntaxError

# Token kinds. The value-carrying ones use their punctuation/word as `kind`
# too, so a switch in the parser can compare against a single string.
STRING = "string"
NUMBER = "number"
IDENT = "ident"
DOT = "."
LBRACKET = "["
RBRACKET = "]"
LPAREN = "("
RPAREN = ")"
COMMA = ","
STAR = "*"
BANG = "!"
AND = "&&"
OR = "||"
EQ = "=="
NEQ = "!="
LT = "<"
GT = ">"
LTE = "<="
GTE = ">="


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: Any  # STRING/NUMBER/IDENT carry their text or parsed value; operators carry None
    offset: int  # byte offset into the expression source


_TWO_CHAR = {
    "&&": AND,
    "||": OR,
    "==": EQ,
    "!=": NEQ,
    "<=": LTE,
    ">=": GTE,
}
_SINGLE = {
    "[": LBRACKET,
    "]": RBRACKET,
    "(": LPAREN,
    ")": RPAREN,
    ",": COMMA,
    "*": STAR,
    ".": DOT,
}
_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "0": "\0",
    "/": "/",
    "\\": "\\",
    "'": "'",
    '"': '"',
}
_HEX = frozenset("0123456789abcdefABCDEF")


def tokenize(src: str) -> list[Token]:
    """Split an expression into tokens. Raises ExprSyntaxError(offset, message)
    on anything the grammar does not contain — a lone `&`, a stray `@`, an
    unterminated string."""
    tokens: list[Token] = []
    i = 0
    byte = 0
    n = len(src)

    while i < n:
        ch = src[i]
        if ch.isspace():
            byte += len(ch.encode())
            i += 1
            continue

        two = src[i : i + 2]
        if two in _TWO_CHAR:
            tokens.append(Token(_TWO_CHAR[two], None, byte))
            i += 2
            byte += 2
            continue

        if ch == "!":
            tokens.append(Token(BANG, None, byte))
            i += 1
            byte += 1
            continue

        if ch in "<>":
            tokens.append(Token(ch, None, byte))
            i += 1
            byte += 1
            continue

        if ch in _SINGLE:
            tokens.append(Token(_SINGLE[ch], None, byte))
            i += 1
            byte += 1
            continue

        if ch in "\"'":
            value, consumed, next_byte = _read_string(src, i, byte)
            tokens.append(Token(STRING, value, byte))
            i = consumed
            byte = next_byte
            continue

        if ch.isdigit():
            number, consumed = _read_number(src, i)
            text = src[i:consumed]
            tokens.append(Token(NUMBER, number, byte))
            i = consumed
            byte += len(text.encode())
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_-"):
                j += 1
            value = src[i:j]
            tokens.append(Token(IDENT, value, byte))
            i = j
            byte += len(value.encode())
            continue

        raise ExprSyntaxError(byte, f"unexpected character {ch!r}")

    return tokens


def _read_string(src: str, start: int, byte: int) -> tuple[str, int, int]:
    quote = src[start]
    j = start + 1
    chars: list[str] = []
    while j < len(src):
        ch = src[j]
        if ch == "\\":
            esc = src[j + 1] if j + 1 < len(src) else ""
            if esc == "u":
                hexpart = src[j + 2 : j + 6]
                if len(hexpart) == 4 and all(c in _HEX for c in hexpart):
                    chars.append(chr(int(hexpart, 16)))
                    j += 6
                    continue
            chars.append(_ESCAPES.get(esc, esc))
            j += 2
            continue
        if ch == quote:
            consumed = j + 1
            return "".join(chars), consumed, byte + len(src[start:consumed].encode())
        chars.append(ch)
        j += 1
    raise ExprSyntaxError(byte, "unterminated string literal")


def _read_number(src: str, start: int) -> tuple[int | float, int]:
    j = start
    while j < len(src) and src[j].isdigit():
        j += 1
    if j + 1 < len(src) and src[j] == "." and src[j + 1].isdigit():
        j += 1
        while j < len(src) and src[j].isdigit():
            j += 1
    text = src[start:j]
    return (float(text) if "." in text else int(text)), j
