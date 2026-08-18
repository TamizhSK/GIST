"""B4 — the Pratt parser. Structure equality against hand-built nodes, plus the
precedence table and every malformed input raising instead of returning junk.
"""

from __future__ import annotations

import dataclasses

import pytest

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
from yeet.expressions.parser import parse


def strip(node: Node) -> Node:
    """Recursively zero every offset so expected trees can be written by hand
    without counting characters."""
    values: dict[str, object] = {}
    for field in dataclasses.fields(node):
        value = getattr(node, field.name)
        if field.name == "offset":
            values[field.name] = 0
        elif isinstance(value, Node):
            values[field.name] = strip(value)
        elif isinstance(value, tuple):
            values[field.name] = tuple(strip(x) if isinstance(x, Node) else x for x in value)
        else:
            values[field.name] = value
    return dataclasses.replace(node, **values)


def lit(value, off=0):
    return Literal(value=value, offset=off)


def ident(name, off=0):
    return Ident(name=name, offset=off)


def mem(target, name, off=0):
    return Member(target=target, name=name, offset=off)


def idx(target, index, off=0):
    return Index(target=target, index=index, offset=off)


def splat(target, off=0):
    return Splat(target=target, offset=off)


def unary(op, operand, off=0):
    return Unary(op=op, operand=operand, offset=off)


def binary(op, left, right, off=0):
    return Binary(op=op, left=left, right=right, offset=off)


def call(name, args, off=0):
    return Call(name=name, args=tuple(args), offset=off)


STRUCTURE: list[tuple[str, Node]] = [
    ("github", ident("github")),
    ("github.sha", mem(ident("github"), "sha")),
    ("steps.my-step.outputs.value", mem(mem(mem(ident("steps"), "my-step"), "outputs"), "value")),
    ("matrix['node']", idx(ident("matrix"), lit("node"))),
    ("a[0]", idx(ident("a"), lit(0))),
    ("jobs.*.outputs", mem(splat(ident("jobs")), "outputs")),
    ("jobs.*.outputs.result", mem(mem(splat(ident("jobs")), "outputs"), "result")),
    ("!x", unary("!", ident("x"))),
    ("true", lit(True)),
    ("TRUE", lit(True)),
    ("false", lit(False)),
    ("null", lit(None)),
    ("42", lit(42)),
    ("3.14", lit(3.14)),
    ("'hello'", lit("hello")),
    ('"hello"', lit("hello")),
    ("(a)", ident("a")),
    ("!(a || b)", unary("!", binary("||", ident("a"), ident("b")))),
    ("f()", call("f", [])),
    ("f(a, b)", call("f", [ident("a"), ident("b")])),
    ("contains(x, 'y')", call("contains", [ident("x"), lit("y")])),
    ("format('{0}', github.sha)", call("format", [lit("{0}"), mem(ident("github"), "sha")])),
    ("a.b.c", mem(mem(ident("a"), "b"), "c")),
    ("a[0][1]", idx(idx(ident("a"), lit(0)), lit(1))),
]


@pytest.mark.parametrize("source,expected", STRUCTURE)
def test_parse_structure(source, expected):
    assert strip(parse(source)) == expected


PRECEDENCE: list[tuple[str, Node]] = [
    ("a || b && c", binary("||", ident("a"), binary("&&", ident("b"), ident("c")))),
    ("a && b == c", binary("&&", ident("a"), binary("==", ident("b"), ident("c")))),
    ("a == b || c", binary("||", binary("==", ident("a"), ident("b")), ident("c"))),
    ("1 < 2 == true", binary("==", binary("<", lit(1), lit(2)), lit(True))),
    ("a == b != c", binary("!=", binary("==", ident("a"), ident("b")), ident("c"))),
    ("!a == b", binary("==", unary("!", ident("a")), ident("b"))),
    ("!a.b", unary("!", mem(ident("a"), "b"))),
    ("a.b == c.d", binary("==", mem(ident("a"), "b"), mem(ident("c"), "d"))),
    ("a <= b < c", binary("<", binary("<=", ident("a"), ident("b")), ident("c"))),
    ("a.b.c[0]", idx(mem(mem(ident("a"), "b"), "c"), lit(0))),
    ("f(a.b, c[0])", call("f", [mem(ident("a"), "b"), idx(ident("c"), lit(0))])),
]


@pytest.mark.parametrize("source,expected", PRECEDENCE)
def test_precedence(source, expected):
    assert strip(parse(source)) == expected


@pytest.mark.parametrize(
    "source",
    [
        "",
        " ",
        "a &&",
        "a b",
        "a ||",
        "a & b",
        "a | b",
        "-1",
        "a.",
        "a..b",
        "a . ",
        "(a",
        "a)",
        "a[",
        "a[0",
        "a[0 1]",
        "f(1, 2",
        "f(1",
        "!",
        "!!",
        "github.sha()",
        ".",
        "&& a",
        "()",
        "a , b",
        "a b c",
        "@",
        "'unterminated",
    ],
)
def test_malformed_inputs_raise(source):
    with pytest.raises(ExprSyntaxError):
        parse(source)


@pytest.mark.parametrize(
    "source,offset",
    [
        ("", 0),
        ("a &&", 4),
        ("a b", 2),
        ("a ||", 4),
        ("a.", 2),
        ("(a", 2),
        ("a[0", 3),
        ("!", 1),
        ("github.sha()", 10),
        ("a , b", 2),
    ],
)
def test_errors_carry_the_offset_inside_the_expression(source, offset):
    with pytest.raises(ExprSyntaxError) as exc:
        parse(source)
    assert exc.value.offset == offset


def test_never_returns_a_partial_tree():
    """Even a syntactically fine prefix must not parse — see `a b` above."""
    assert strip(parse("github.ref_name")) == mem(ident("github"), "ref_name")
    with pytest.raises(ExprSyntaxError):
        parse("github.ref_name garbage")
