"""The demo metric: real OSS workflows parse without E1xx/E2xx.

`tests/corpus/` holds byte-exact vendored workflows from real repositories (see
the README there for provenance). Every file must survive the parse path —
layers 0/1 (file + YAML) and layer 2 (schema) — and build an IR. The assertion
is deliberately on E1xx/E2xx only: layer 3 semantics and layer 4 lints are a
different gate (`yeet check`), and firing E3xx/W4xx on a stranger's real
workflow is often correct behavior, not a parse hole.

This is the test that catches what hand-written fixtures cannot: a fixture we
write exercises the schema we wrote; a workflow we didn't write exercises the
schema the world actually uses. The very first corpus additions found five
holes nothing else had (root/job `permissions` and `concurrency`, job
`services`, job-level `continue-on-error`, scalar `env` values, and
expression-valued `timeout-minutes`).

Owner: Dev A
Tier: test — may import from anything
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.validation.pipeline import validate_file

CORPUS = Path(__file__).parents[1] / "corpus"
CASES = sorted(p.name for p in CORPUS.glob("*.yml") if not p.name.startswith("README")) + sorted(
    p.name for p in CORPUS.glob("*.yaml")
)

PARSE_CODES = ("YEET-E1", "YEET-E2")


def _parse_errors(case: str) -> list[str]:
    path = CORPUS / case
    bag, workflow = validate_file(path, upto=2)
    bad = [d.code for d in bag.items if d.code.startswith(PARSE_CODES)]
    assert workflow is not None or not bad, (
        f"{case}: a parse error stopped the pipeline before the IR was built"
    )
    return bad


@pytest.mark.parametrize("case", CASES)
def test_corpus_parses_without_e1_e2(case):
    """The metric. Each vendored real workflow must pass the parse gate."""
    bad = _parse_errors(case)
    assert not bad, f"{case} failed the parse gate: {bad}"


@pytest.mark.parametrize("case", CASES)
def test_corpus_builds_ir(case):
    """Parsing isn't enough — the builder must survive the file too."""
    path = CORPUS / case
    bag, workflow = validate_file(path, upto=3)
    bad = [d.code for d in bag.items if d.code.startswith(PARSE_CODES)]
    assert not bad, f"{case} failed the parse gate: {bad}"
    assert workflow is not None, f"{case} built no IR (a YEET-E900?)"


def test_corpus_metric_is_above_the_floor():
    """The demo quotes a number; keep it honest and above 80%."""
    passed = sum(not _parse_errors(case) for case in CASES)
    ratio = passed / len(CASES)
    assert ratio >= 0.8, f"parse metric fell to {ratio:.0%} ({passed}/{len(CASES)})"
