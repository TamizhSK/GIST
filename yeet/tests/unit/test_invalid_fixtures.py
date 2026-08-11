"""A10 + A13 — `tests/invalid/<code>.yml` fires exactly that code.

Each fixture walks the same layers as the real pipeline, composed directly
(Dev D's pipeline stub is not wired yet): loader -> aliases -> layer2 schema
-> builder. Assert the bag contains exactly `YEET-<stem>` and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.core.diagnostics import DiagnosticBag
from yeet.parser.aliases import normalize
from yeet.parser.builder import build_workflow
from yeet.parser.loader import load_with_positions
from yeet.validation.layer2_schema import check as layer2_check

INVALID = Path(__file__).parents[1] / "invalid"
CASES = sorted(p.name for p in INVALID.glob("*.yml"))


@pytest.mark.parametrize("case", CASES)
def test_invalid_fixture_fires_only_its_code(case):
    path = INVALID / case
    bag = DiagnosticBag()
    data = load_with_positions(path, bag)
    codes = {d.code for d in bag.items}

    if data is not None and not bag.has_errors():
        data, _ = normalize(data)
        codes |= {d.code for d in layer2_check(data, path).items}
        if data is not None:
            build_workflow(data, path, bag)
            codes |= {d.code for d in bag.items}

    assert codes == {f"YEET-{path.stem}"}
