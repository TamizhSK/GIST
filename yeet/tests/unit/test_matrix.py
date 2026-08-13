"""B10: strategy.matrix -> concrete legs.

The canonical reference is the GitHub docs "Expanding or adding matrix
configurations" example: fruit=[apple, pear] x animal=[cat, dog] with five
include entries yields exactly six legs, in exactly this order. Anything that
changes that list is a compatibility break.

Owner: Dev B
"""

from __future__ import annotations

from typing import Any

from conftest import POS, make_job

from yeet.core.ir import Strategy
from yeet.planner.matrix import expand


def legs(
    *,
    matrix: dict[str, list[Any]] | None = None,
    include: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    strategy = Strategy(
        pos=POS,
        matrix=matrix or {},
        include=include or [],
        exclude=exclude or [],
    )
    return expand(make_job(strategy=strategy))


def test_no_strategy_is_a_single_empty_leg() -> None:
    assert expand(make_job()) == [{}]


def test_empty_matrix_is_a_single_empty_leg() -> None:
    assert legs(matrix={}) == [{}]


def test_cartesian_product_order_first_key_varies_slowest() -> None:
    assert legs(matrix={"version": [10, 12, 14], "os": ["ubuntu", "windows"]}) == [
        {"version": 10, "os": "ubuntu"},
        {"version": 10, "os": "windows"},
        {"version": 12, "os": "ubuntu"},
        {"version": 12, "os": "windows"},
        {"version": 14, "os": "ubuntu"},
        {"version": 14, "os": "windows"},
    ]


def test_single_value_matrix() -> None:
    assert legs(matrix={"fruit": ["apple"]}) == [{"fruit": "apple"}]


def test_exclude_removes_only_matching_product_legs() -> None:
    assert legs(
        matrix={
            "os": ["macos", "windows"],
            "version": [12, 16],
            "environment": ["staging", "production"],
        },
        exclude=[
            {"os": "macos", "version": 12, "environment": "production"},
            {"os": "windows", "version": 16},
        ],
    ) == [
        {"os": "macos", "version": 12, "environment": "staging"},
        {"os": "macos", "version": 16, "environment": "staging"},
        {"os": "macos", "version": 16, "environment": "production"},
        {"os": "windows", "version": 12, "environment": "staging"},
        {"os": "windows", "version": 12, "environment": "production"},
    ]


def test_docs_include_example_exact_legs() -> None:
    assert legs(
        matrix={"fruit": ["apple", "pear"], "animal": ["cat", "dog"]},
        include=[
            {"color": "green"},
            {"color": "pink", "animal": "cat"},
            {"fruit": "apple", "shape": "circle"},
            {"fruit": "banana"},
            {"fruit": "banana", "animal": "cat"},
        ],
    ) == [
        {"fruit": "apple", "animal": "cat", "color": "pink", "shape": "circle"},
        {"fruit": "apple", "animal": "dog", "color": "green", "shape": "circle"},
        {"fruit": "pear", "animal": "cat", "color": "pink"},
        {"fruit": "pear", "animal": "dog", "color": "green"},
        {"fruit": "banana"},
        {"fruit": "banana", "animal": "cat"},
    ]


def test_include_overwrites_previous_include_not_original_product() -> None:
    assert legs(
        matrix={"fruit": ["apple"]},
        include=[
            {"color": "green"},
            {"color": "pink"},
        ],
    ) == [
        {"fruit": "apple", "color": "pink"},
    ]


def test_include_equal_value_is_not_an_overwrite() -> None:
    assert legs(
        matrix={"fruit": ["apple"]},
        include=[{"fruit": "apple", "color": "red"}],
    ) == [{"fruit": "apple", "color": "red"}]


def test_include_new_legs_are_not_merge_targets() -> None:
    assert legs(
        matrix={"fruit": ["apple"]},
        include=[
            {"fruit": "banana"},
            {"fruit": "banana", "animal": "cat"},
        ],
    ) == [
        {"fruit": "apple"},
        {"fruit": "banana"},
        {"fruit": "banana", "animal": "cat"},
    ]


def test_include_runs_after_exclude_and_resurrects_legs() -> None:
    assert legs(
        matrix={"os": ["linux"]},
        exclude=[{"os": "linux"}],
        include=[{"os": "linux"}],
    ) == [{"os": "linux"}]


def test_include_appended_legs_follow_product_order() -> None:
    assert legs(
        matrix={"fruit": ["apple"]},
        include=[
            {"color": "red"},
            {"fruit": "banana"},
            {"fruit": "banana", "shape": "circle"},
        ],
    ) == [
        {"fruit": "apple", "color": "red"},
        {"fruit": "banana"},
        {"fruit": "banana", "shape": "circle"},
    ]


def test_an_include_only_matrix_gives_one_leg_per_entry() -> None:
    """No base variables at all — `include:` IS the matrix.

    Three of the nine real workflows in tests/corpus/ are shaped this way
    (Flask, Jinja, scikit-learn). `expand` used to return `[{}]`: it bailed out
    on an empty `matrix` before it ever looked at `include`, so Flask's nine
    Python versions planned as ONE unparameterised job that quietly tested
    whatever `python` happened to be on the runner.
    """
    job = make_job(
        "tests",
        strategy=Strategy(
            pos=POS,
            matrix={},
            include=[
                {"python": "3.13"},
                {"python": "3.12"},
                {"name": "Mac", "python": "3.12", "os": "macos-latest"},
            ],
        ),
    )

    assert expand(job) == [
        {"python": "3.13"},
        {"python": "3.12"},
        {"name": "Mac", "python": "3.12", "os": "macos-latest"},
    ]


def test_a_strategy_with_neither_matrix_nor_include_is_still_one_leg() -> None:
    job = make_job("tests", strategy=Strategy(pos=POS, matrix={}))
    assert expand(job) == [{}]
