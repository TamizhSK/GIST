"""Expression table tests: a CSV of `expr, context, expected`.

architecture.md 8: dozens of cases, one test function. Adding a row is adding
a line to `data/expression_table.csv` — no code. The `context` column is a
JSON object whose keys are `Contexts` field names.

Owner: Dev B
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from yeet.expressions.contexts import Contexts
from yeet.expressions.evaluator import evaluate
from yeet.expressions.parser import parse

TABLE = Path(__file__).parent / "data" / "expression_table.csv"


def _rows() -> list[tuple[str, str, str]]:
    with TABLE.open(newline="", encoding="utf-8") as fh:
        return [(r["expr"], r["context"], r["expected"]) for r in csv.DictReader(fh)]


@pytest.mark.parametrize("expr,context_json,expected_json", _rows())
def test_expression_table(expr: str, context_json: str, expected_json: str) -> None:
    ctx = Contexts(**json.loads(context_json))
    assert evaluate(parse(expr), ctx) == json.loads(expected_json)
