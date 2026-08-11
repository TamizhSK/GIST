"""B7 — the expression builtins, called directly (not through the parser)."""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.expressions import functions
from yeet.expressions.contexts import Contexts
from yeet.expressions.functions import (
    always,
    cancelled,
    contains,
    ends_with,
    failure,
    format_value,
    from_json,
    hash_files_from,
    join,
    starts_with,
    success,
    to_json,
)


def ctx(needs=None, root=None) -> Contexts:
    return Contexts(needs=needs or {}, root=root or Path.cwd())


# --- contains -----------------------------------------------------------------


def test_contains_string_substring_case_insensitive():
    assert contains(["Hello World", "hello"], ctx()) is True
    assert contains(["Hello World", "world!"], ctx()) is False
    assert contains(["Hello World", ""], ctx()) is True


def test_contains_array_membership_uses_loose_equality():
    assert contains([[1, 2, 3], 2], ctx()) is True
    assert contains([[1, 2, 3], "2"], ctx()) is True
    assert contains([[1, 2, 3], 9], ctx()) is False


def test_contains_case_insensitive_in_array():
    assert contains([["a", "B"], "b"], ctx()) is True


def test_contains_rejects_non_searchable():
    with pytest.raises(ValueError):
        contains([42, 1], ctx())
    with pytest.raises(ValueError):
        contains(["only one"], ctx())


# --- startsWith / endsWith ----------------------------------------------------


def test_starts_and_ends_with_case_insensitive():
    assert starts_with(["Hello", "he"], ctx()) is True
    assert starts_with(["Hello", "lo"], ctx()) is False
    assert ends_with(["Hello", "LO"], ctx()) is True
    assert ends_with(["Hello", "he"], ctx()) is False


def test_starts_ends_with_reject_non_strings():
    with pytest.raises(ValueError):
        starts_with([5, "5"], ctx())
    with pytest.raises(ValueError):
        ends_with(["5", 5], ctx())


# --- format -------------------------------------------------------------------


def test_format_basic_and_repeats():
    assert format_value(["Hello {0} {1}", "World", "!"], ctx()) == "Hello World !"
    assert format_value(["{0}-{0}", "x"], ctx()) == "x-x"


def test_format_missing_and_null_become_empty():
    assert format_value(["a{0}b{1}", None], ctx()) == "ab"
    assert format_value(["{0} {1}", "x"], ctx()) == "x "
    assert format_value(["{7}", "unused"], ctx()) == ""


def test_format_stringifies_booleans():
    assert format_value(["{0}", True], ctx()) == "true"
    assert format_value(["{0}", False], ctx()) == "false"


def test_format_rejects_non_string_template():
    with pytest.raises(ValueError):
        format_value([42], ctx())


# --- join ---------------------------------------------------------------------


def test_join_default_separator_is_comma():
    assert join([["a", "b", "c"]], ctx()) == "a,b,c"


def test_join_custom_separator():
    assert join([[1, 2, 3], "-"], ctx()) == "1-2-3"


def test_join_null_and_non_string_elements_are_empty():
    assert join([[None, "a", 5], ","], ctx()) == ",a,5"


def test_join_rejects_non_array():
    with pytest.raises(ValueError):
        join(["not-an-array"], ctx())


# --- JSON ---------------------------------------------------------------------


def test_to_json_roundtrip():
    assert to_json([{"a": 1, "b": None, "c": True}], ctx()) == '{"a":1,"b":null,"c":true}'


def test_from_json_types():
    assert from_json(["42"], ctx()) == 42
    assert from_json(["true"], ctx()) is True
    assert from_json(["null"], ctx()) is None
    assert from_json(['[1, "two"]'], ctx()) == [1, "two"]


def test_from_json_invalid_raises():
    with pytest.raises(ValueError):
        from_json(["not json"], ctx())
    with pytest.raises(ValueError):
        from_json([42], ctx())


# --- status functions ---------------------------------------------------------


def test_always_and_cancelled():
    assert always([], ctx()) is True
    assert cancelled([], ctx()) is False


def test_success_and_failure_read_needs():
    ok = ctx(needs={"a": {"result": "success"}, "b": {"result": "success"}})
    assert success([], ok) is True
    assert failure([], ok) is False

    broken = ctx(needs={"a": {"result": "success"}, "b": {"result": "failure"}})
    assert success([], broken) is False
    assert failure([], broken) is True


def test_status_functions_reject_arguments():
    with pytest.raises(ValueError):
        success([True], ctx())
    with pytest.raises(ValueError):
        always(["x"], ctx())


# --- hashFiles ----------------------------------------------------------------


def test_hash_files_is_deterministic(tmp_path):
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")

    first = hash_files_from(["*.txt"], tmp_path)
    second = hash_files_from(["*.txt"], tmp_path)
    assert first == second
    assert len(first) == 64  # SHA-256 hex


def test_hash_files_order_does_not_matter(tmp_path):
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")

    forwards = hash_files_from(["a.txt", "b.txt"], tmp_path)
    backwards = hash_files_from(["b.txt", "a.txt"], tmp_path)
    assert forwards == backwards


def test_hash_files_same_content_same_hash(tmp_path):
    # Two different directories, same relative files -> same hash.
    for dirname in ("a", "b"):
        root = tmp_path / dirname
        (root / "src").mkdir(parents=True)
        (root / "src" / "x.txt").write_text("same", encoding="utf-8")
    assert hash_files_from(["src/x.txt"], tmp_path / "a") == hash_files_from(
        ["src/x.txt"], tmp_path / "b"
    )


def test_hash_files_content_change_changes_hash(tmp_path):
    (tmp_path / "f.txt").write_text("v1", encoding="utf-8")
    before = hash_files_from(["f.txt"], tmp_path)
    (tmp_path / "f.txt").write_text("v2", encoding="utf-8")
    assert hash_files_from(["f.txt"], tmp_path) != before


def test_hash_files_empty_when_nothing_matches(tmp_path):
    assert hash_files_from(["**/*.nope"], tmp_path) == ""


def test_hash_files_skips_directories(tmp_path):
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "f.txt").write_text("x", encoding="utf-8")
    assert len(hash_files_from(["**/*"], tmp_path)) == 64


# --- registry -----------------------------------------------------------------


def test_lookup_is_case_insensitive():
    assert functions.lookup("STARTSWITH") is starts_with
    assert functions.lookup("format") is format_value


def test_lookup_unknown_returns_null_stub():
    assert functions.lookup("nope")(["ignored"], ctx()) is None


def test_registry_has_the_documented_functions():
    for name in (
        "contains",
        "startswith",
        "endswith",
        "format",
        "join",
        "tojson",
        "fromjson",
        "hashfiles",
        "success",
        "failure",
        "always",
        "cancelled",
    ):
        assert name in functions.FUNCTIONS
