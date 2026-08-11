"""GitHub's loose-equality and numeric coercion, shared by the evaluator and
the function registry (which both need it; a separate module avoids a cycle).

The rules, from docs.github.com "Expressions":

* matching types: strings compare case-insensitively; numbers numerically
  (`NaN == NaN` is false); objects/arrays only equal when they are the same
  instance.
* mismatched types: both coerced to a number, then compared:
  null -> 0, true -> 1, false -> 0, string -> parsed as a legal JSON number
  format (empty string -> 0, anything else -> NaN), array/object -> NaN.
* a `NaN` operand makes every relational comparison false.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import json
import math

Number = int | float


def as_number(value: object) -> Number:
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        if value == "":
            return 0
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return math.nan
        if isinstance(parsed, bool) or not isinstance(parsed, (int, float)):
            return math.nan
        return parsed
    return math.nan


def loose_equal(a: object, b: object) -> bool:
    """`'1' == 1` is true; `'abc' == 'ABC'` is true; `NaN == NaN` is false."""
    if isinstance(a, bool) or isinstance(b, bool):
        return as_number(a) == as_number(b)
    if a is None and b is None:
        return True
    if type(a) is not type(b):
        return as_number(a) == as_number(b)
    if isinstance(a, str):
        assert isinstance(b, str)  # same-type check above guarantees it
        return a.casefold() == b.casefold()
    if isinstance(a, (int, float)):
        assert isinstance(b, (int, float))
        return a == b  # IEEE NaN != NaN falls out for free
    if isinstance(a, (list, dict)):
        return a is b
    return bool(a == b)


def compare(op: str, a: object, b: object) -> bool:
    """`<` `<=` `>` `>=` — JavaScript semantics, which GitHub inherits.

    Two strings compare lexicographically (`'5' > '10'` is false — the famous
    trap that `fromJSON()` exists to escape). Anything else coerces to a
    number, and any NaN operand yields False.
    """
    if isinstance(a, str) and isinstance(b, str):
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a >= b
    left = as_number(a)
    right = as_number(b)
    if math.isnan(left) or math.isnan(right):
        return False
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    return left >= right
