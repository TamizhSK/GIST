"""A10 + A13 — `tests/invalid/<code>.yml` fires exactly that code.

Driven through `validate_file`, the function the CLI actually calls, NOT by
composing loader -> aliases -> layer2 -> builder by hand. That hand-composed
version is how `aliases.normalize()` went four review sessions with no call
site in the product while its tests stayed green: the test performed the step
the pipeline had forgotten. A fixture suite that builds its own pipeline can
only prove the layers work in an order nobody runs.

`upto=3` stops before layer 4, so a fixture is not required to be lint-clean
to pin its own code — the lints have their own suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.validation.pipeline import validate_file

INVALID = Path(__file__).parents[1] / "invalid"
CASES = sorted(p.name for p in INVALID.glob("*.yml"))


@pytest.mark.parametrize("case", CASES)
def test_invalid_fixture_fires_only_its_code(case):
    path = INVALID / case
    bag, _ = validate_file(path, upto=3)

    assert {d.code for d in bag.items} == {f"YEET-{path.stem}"}
