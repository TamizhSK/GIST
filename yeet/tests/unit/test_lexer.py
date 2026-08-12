"""B2 — the tokenizer. Table tests, one stream per row.

Each row is (source, [(kind, value), ...]). A bare kind with no value means
`value is None` (an operator/punctuation token).
"""

from __future__ import annotations

import pytest

from yeet.expressions import lexer
from yeet.expressions.ast_nodes import ExprSyntaxError

NONE = lexer.NUMBER
STR = lexer.STRING
ID = lexer.IDENT

CASES: list[tuple[str, list[tuple[str, object]]]] = [
    ("", []),
    (" ", []),
    ("github", [(ID, "github")]),
    ("github.sha", [(ID, "github"), (".", None), (ID, "sha")]),
    (
        "steps.my-step.outputs.value",
        [
            (ID, "steps"),
            (".", None),
            (ID, "my-step"),
            (".", None),
            (ID, "outputs"),
            (".", None),
            (ID, "value"),
        ],
    ),
    ("matrix['node']", [(ID, "matrix"), ("[", None), (STR, "node"), ("]", None)]),
    ("a[0]", [(ID, "a"), ("[", None), (NONE, 0), ("]", None)]),
    ("f(a, b)", [(ID, "f"), ("(", None), (ID, "a"), (",", None), (ID, "b"), (")", None)]),
    ("!x", [("!", None), (ID, "x")]),
    ("a && b || c", [(ID, "a"), ("&&", None), (ID, "b"), ("||", None), (ID, "c")]),
    ("a == b != c", [(ID, "a"), ("==", None), (ID, "b"), ("!=", None), (ID, "c")]),
    (
        "a < b <= c > d >= e",
        [
            (ID, "a"),
            ("<", None),
            (ID, "b"),
            ("<=", None),
            (ID, "c"),
            (">", None),
            (ID, "d"),
            (">=", None),
            (ID, "e"),
        ],
    ),
    ("jobs.*.outputs", [(ID, "jobs"), (".", None), ("*", None), (".", None), (ID, "outputs")]),
    ("true", [(ID, "true")]),
    ("false", [(ID, "false")]),
    ("null", [(ID, "null")]),
    ("42", [(NONE, 42)]),
    ("3.14", [(NONE, 3.14)]),
    ('"hello"', [(STR, "hello")]),
    ("'hello'", [(STR, "hello")]),
    ('"a\\"b"', [(STR, 'a"b')]),
    ("'it\\'s'", [(STR, "it's")]),
    (r'"tab\there"', [(STR, "tab\there")]),
    (r'"nl\nhere"', [(STR, "nl\nhere")]),
    (r'"unicode\u00e9"', [(STR, "unicode\u00e9")]),
    ("env.MY_VAR", [(ID, "env"), (".", None), (ID, "MY_VAR")]),
    ("github.ref_name", [(ID, "github"), (".", None), (ID, "ref_name")]),
    (
        "a.b.c.d",
        [(ID, "a"), (".", None), (ID, "b"), (".", None), (ID, "c"), (".", None), (ID, "d")],
    ),
    ("_x", [(ID, "_x")]),
    ("  spaced  out  ", [(ID, "spaced"), (ID, "out")]),
    ("hashFiles('**/*.js')", [(ID, "hashFiles"), ("(", None), (STR, "**/*.js"), (")", None)]),
    (
        "fromJSON('{\"a\":1}').a",
        [(ID, "fromJSON"), ("(", None), (STR, '{"a":1}'), (")", None), (".", None), (ID, "a")],
    ),
    ("a['x y']", [(ID, "a"), ("[", None), (STR, "x y"), ("]", None)]),
    ("(a)", [("(", None), (ID, "a"), (")", None)]),
    ("123.45.67", [(NONE, 123.45), (".", None), (NONE, 67)]),
    ("a<=b", [(ID, "a"), ("<=", None), (ID, "b")]),
    ("a>=b", [(ID, "a"), (">=", None), (ID, "b")]),
]


@pytest.mark.parametrize("source,expected", CASES)
def test_token_streams(source, expected):
    got = [(t.kind, t.value) for t in lexer.tokenize(source)]
    assert got == expected


@pytest.mark.parametrize(
    "source",
    [
        "a & b",  # single & is not an operator
        "a | b",  # single | is not an operator
        "-1",  # GH expressions have no unary minus
        "@x",
        "#",
        "$",
        '"unterminated',
        "'unterminated",
    ],
)
def test_unexpected_characters_raise(source):
    with pytest.raises(ExprSyntaxError):
        lexer.tokenize(source)


def test_unterminated_string_reports_the_start_offset():
    with pytest.raises(ExprSyntaxError) as exc:
        lexer.tokenize("    'nope")
    assert exc.value.offset == 4


def test_offsets_are_reported_in_byte_position():
    """A multi-byte character before a token must push its byte offset past the
    character index — the whole point of byte offsets."""
    tokens = lexer.tokenize("'é' !x")
    bang = tokens[1]
    assert bang.offset == len("'é' ".encode())


def test_expression_punctuation_offsets():
    tokens = lexer.tokenize("a && b")
    assert [t.offset for t in tokens] == [0, 2, 5]
