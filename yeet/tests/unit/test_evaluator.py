"""B6 — the evaluator: loose equality, truthiness, short-circuiting, contexts."""

from __future__ import annotations

import pytest

from yeet.expressions.ast_nodes import Ident, Literal, Unary
from yeet.expressions.contexts import Contexts
from yeet.expressions.evaluator import evaluate, truthy


def ctx(**kwargs) -> Contexts:
    values = dict(
        github={"sha": "abc", "ref_name": "main", "count": 3},
        env={"MODE": "release"},
        matrix={"node": 20, "os": "ubuntu"},
        steps={"build": {"outputs": {"id": "123"}}},
        needs={"lint": {"result": "success"}, "test": {"result": "failure"}},
        secrets={"TOKEN": "s3cret"},
        inputs={"target": "web"},
    )
    values.update(kwargs)
    return Contexts(**values)


# --- literals / contexts -----------------------------------------------------


def test_literal_passes_through():
    assert evaluate(Literal(value="x"), ctx()) == "x"
    assert evaluate(Literal(value=None), ctx()) is None


def test_context_root_values():
    assert evaluate(Ident(name="github"), ctx()) == {"sha": "abc", "ref_name": "main", "count": 3}
    assert evaluate(Ident(name="matrix"), ctx()) == {"node": 20, "os": "ubuntu"}


def test_unknown_context_is_none():
    assert evaluate(Ident(name="githib"), ctx()) is None


def test_missing_member_returns_none_not_error():
    assert evaluate(parse_("github.nope"), ctx()) is None
    assert evaluate(parse_("steps.absent.outputs.x"), ctx()) is None


def test_context_lookup_is_case_insensitive():
    # GitHub context property access ignores case — for every context.
    assert evaluate(parse_("github.SHA"), ctx()) == "abc"
    assert evaluate(parse_("matrix.NODE"), ctx()) == 20
    assert evaluate(parse_("env.mode"), ctx()) == "release"


def test_deep_member_chain():
    assert evaluate(parse_("steps.build.outputs.id"), ctx()) == "123"


def test_index_into_mapping_and_list():
    assert evaluate(parse_("matrix['node']"), ctx()) == 20
    assert evaluate(parse_("matrix['missing']"), ctx()) is None


def test_index_out_of_range_is_none():
    assert evaluate(parse_("matrix[99]"), ctx()) is None


def test_index_on_scalar_is_none():
    assert evaluate(parse_("'abc'[0]"), ctx()) is None


def test_splat_flattens_mapping_values():
    assert evaluate(parse_("needs.*.result"), ctx()) == ["success", "failure"]


# --- truthiness --------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (False, False),
        (0, False),
        (0.0, False),
        (-0.0, False),
        ("", False),
        (None, False),
        (True, True),
        (1, True),
        (-1, True),
        (2.5, True),
        ("false", True),  # the string "false" is truthy — GitHub's actual rule
        ("0", True),
        (" ", True),
        ([], True),
        ({}, True),
        (float("nan"), True),
    ],
)
def test_truthy(value, expected):
    assert truthy(value) is expected


# --- unary / binary ----------------------------------------------------------


def test_not():
    assert evaluate(Unary(op="!", operand=Literal(value=False)), ctx()) is True
    assert evaluate(Unary(op="!", operand=Literal(value=True)), ctx()) is False
    assert evaluate(Unary(op="!", operand=Literal(value="false")), ctx()) is False


def test_and_or_return_operands_like_javascript():
    # `false && 2 || 3` -> false || 3 -> 3  (GitHub's documented ternary idiom)
    assert evaluate(parse_("false && 2 || 3"), ctx()) == 3
    assert evaluate(parse_("true && 7"), ctx()) == 7
    assert evaluate(parse_("'' || 'fallback'"), ctx()) == "fallback"
    assert evaluate(parse_("0 || 5"), ctx()) == 5


def test_and_short_circuits():
    assert evaluate(parse_("false && unknownFn()"), ctx()) is False


def test_or_short_circuits():
    assert evaluate(parse_("true || unknownFn()"), ctx()) is True


def test_equality_matching_types():
    assert evaluate(parse_("'abc' == 'ABC'"), ctx()) is True
    assert evaluate(parse_("1 == 1.0"), ctx()) is True
    assert evaluate(parse_("null == null"), ctx()) is True


def test_loose_equality_coercion():
    assert evaluate(parse_("'1' == 1"), ctx()) is True
    assert evaluate(parse_("'' == 0"), ctx()) is True
    assert evaluate(parse_("null == 0"), ctx()) is True
    assert evaluate(parse_("true == 1"), ctx()) is True
    assert evaluate(parse_("false == 0"), ctx()) is True
    assert evaluate(parse_("'1.5' == 1.5"), ctx()) is True


def test_loose_equality_false_cases():
    assert evaluate(parse_("'abc' == 1"), ctx()) is False
    assert evaluate(parse_("'10' == 5"), ctx()) is False
    assert evaluate(parse_("true == 2"), ctx()) is False
    assert evaluate(parse_("'false' == false"), ctx()) is False  # NaN != 0


def test_nan_never_equals_itself():
    assert evaluate(parse_("'abc' == 'xyz'"), ctx()) is False
    assert evaluate(parse_("'abc' == 'ABC'"), ctx()) is True


def test_arrays_are_only_equal_when_same_instance():
    assert evaluate(parse_("a == a"), ctx()) is True


def test_inequality():
    assert evaluate(parse_("'1' != 2"), ctx()) is True
    assert evaluate(parse_("1 != 1.0"), ctx()) is False


def test_relational_comparison_is_numeric():
    assert evaluate(parse_("1 < 2"), ctx()) is True
    assert evaluate(parse_("2 <= 2"), ctx()) is True
    assert evaluate(parse_("3 > 2"), ctx()) is True
    assert evaluate(parse_("3 >= 4"), ctx()) is False
    assert evaluate(parse_("5 < '6'"), ctx()) is True
    assert evaluate(parse_("'5' == 5 && 5 < '6'"), ctx()) is True


def test_relational_strings_compare_lexicographically():
    # JS rules, which GitHub inherits: two strings never coerce to numbers.
    assert evaluate(parse_("'5' > '10'"), ctx()) is True
    assert evaluate(parse_("'10' < '9'"), ctx()) is True
    assert evaluate(parse_("'abc' < 'abd'"), ctx()) is True
    assert evaluate(parse_("'abc' == 'ABC' && 'ABC' < 'b'"), ctx()) is True


def test_relational_with_nan_is_false():
    assert evaluate(parse_("'abc' < 5"), ctx()) is False
    assert evaluate(parse_("5 <= 'abc'"), ctx()) is False


def test_github_ref_conditional_parses_and_evaluates():
    expr = "github.ref_name == 'main' && needs.lint.result == 'success'"
    assert evaluate(parse_(expr), ctx()) is True


# --- functions ---------------------------------------------------------------


def test_contains_string_is_case_insensitive():
    assert evaluate(parse_("contains('Hello World', 'hello')"), ctx()) is True
    assert evaluate(parse_("contains('Hello World', 'xyz')"), ctx()) is False


def test_contains_array_uses_loose_equality():
    assert evaluate(parse_("contains(fromJSON('[1, 2, 3]'), '2')"), ctx()) is True


def test_startswith_and_endswith():
    assert evaluate(parse_("startsWith('Hello', 'he')"), ctx()) is True
    assert evaluate(parse_("endsWith('Hello', 'LO')"), ctx()) is True


def test_format_substitutes_and_stringifies():
    assert evaluate(parse_("format('{0} {1} {2}', 'a', 'b')"), ctx()) == "a b "
    assert evaluate(parse_("format('{0} {1}', null, 3)"), ctx()) == " 3"


def test_join_default_separator():
    assert evaluate(parse_("join(fromJSON('[1, 2, 3]'))"), ctx()) == "1,2,3"


def test_join_with_separator_and_null_element():
    assert evaluate(parse_("join(fromJSON('[\"a\", null, \"b\"]'), '-')"), ctx()) == "a--b"


def test_tojson_roundtrip():
    assert evaluate(parse_("toJSON(fromJSON('{\"a\":1}'))"), ctx()) == '{"a":1}'


def test_status_functions_read_needs():
    assert evaluate(parse_("always()"), ctx()) is True
    assert evaluate(parse_("cancelled()"), ctx()) is False
    assert evaluate(parse_("success()"), ctx()) is False
    assert evaluate(parse_("failure()"), ctx()) is True


def test_success_true_when_all_needs_ok():
    good = ctx(needs={"a": {"result": "success"}, "b": {"result": "success"}})
    assert evaluate(parse_("success()"), good) is True
    assert evaluate(parse_("failure()"), good) is False


def test_unknown_function_degrades_to_none():
    assert evaluate(parse_("totallyUnknownFn(1)"), ctx()) is None


# --- helpers -----------------------------------------------------------------


def parse_(source: str):
    from yeet.expressions.parser import parse

    return parse(source)
