"""The dialect and canonical GitHub Actions must build the SAME IR.

"A superset, not a replacement" (plan.md §10) is only true if `vibe:` and
`name:` are genuinely the same key by the time anything downstream sees them.
The way that claim breaks is not a wrong translation — `aliases.yml` is a flat
table and hard to get wrong — but a *missing call*: `normalize()` existed,
was unit-tested, and had no call site in `validation/pipeline.py` for four
sessions, so every dialect file failed `yeet check` with E201 while the golden
tests (which call `normalize()` by hand) stayed green.

So these tests go through `validate_file` — the real entry point — rather than
composing the stages themselves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.validation.pipeline import validate_file

DIALECT = """\
vibe: build and test
when:
  push:
    branches: [main]
drip:
  NODE_ENV: production
the_grind:
  build:
    cooked_on: ubuntu-22.04
    moves:
      - vibe: checkout
        yoink: ./.yeet/actions/checkout
      - vibe: test
        bet: pytest -q
        where: ./src
        delulu: true
  deploy:
    cooked_on: ubuntu-22.04
    after: [build]
    only_if: success()
    moves:
      - bet: echo shipping
"""

CANONICAL = """\
name: build and test
on:
  push:
    branches: [main]
env:
  NODE_ENV: production
jobs:
  build:
    runs-on: ubuntu-22.04
    steps:
      - name: checkout
        uses: ./.yeet/actions/checkout
      - name: test
        run: pytest -q
        working-directory: ./src
        continue-on-error: true
  deploy:
    runs-on: ubuntu-22.04
    needs: [build]
    if: success()
    steps:
      - run: echo shipping
"""


def _build(tmp_path: Path, text: str, name: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    bag, workflow = validate_file(path, upto=3)
    assert workflow is not None, [d.code for d in bag.items]
    assert not bag.has_errors(), [(d.code, d.message) for d in bag.errors]
    return workflow


def _shape(workflow) -> dict:
    """Everything except the bits that legitimately differ (source path,
    positions, and the used_dialect flag itself)."""
    return {
        "name": workflow.name,
        "env": dict(workflow.env),
        "triggers": sorted(t.event for t in workflow.triggers),
        "jobs": {
            key: {
                "runs_on": job.runs_on,
                "needs": list(job.needs),
                "if": job.if_,
                "steps": [
                    {
                        "name": step.name,
                        "run": step.run,
                        "uses": step.uses,
                        "working_directory": step.working_directory,
                        "continue_on_error": step.continue_on_error,
                    }
                    for step in job.steps
                ],
            }
            for key, job in workflow.jobs.items()
        },
    }


def test_dialect_and_canonical_produce_identical_ir(tmp_path: Path) -> None:
    dialect = _build(tmp_path, DIALECT, "dialect.yml")
    canonical = _build(tmp_path, CANONICAL, "canonical.yml")
    assert _shape(dialect) == _shape(canonical)


def test_used_dialect_is_set_only_for_the_dialect(tmp_path: Path) -> None:
    """The flag I415 ("mixed dialect and canonical keys") depends on."""
    assert _build(tmp_path, DIALECT, "dialect.yml").used_dialect is True
    assert _build(tmp_path, CANONICAL, "canonical.yml").used_dialect is False


@pytest.mark.parametrize(
    ("alias", "canonical_key"),
    [
        ("vibe", "name"),
        ("when", "on"),
        ("the_grind", "jobs"),
        ("cooked_on", "runs-on"),
        ("moves", "steps"),
        ("bet", "run"),
        ("yoink", "uses"),
        ("after", "needs"),
        ("only_if", "if"),
        ("drip", "env"),
    ],
)
def test_every_headline_alias_is_in_the_table(alias: str, canonical_key: str) -> None:
    """A cheap guard on `aliases.yml`: these ten appear in the README, the
    plan's examples and the demo script, so removing one breaks documentation
    rather than just a workflow."""
    from yeet.parser.aliases import alias_map

    assert alias_map().get(alias) == canonical_key


def test_the_walking_skeleton_validates_clean(tmp_path: Path) -> None:
    """The exact workflow in plan.md §6 — the one that used to emit 5 errors."""
    path = tmp_path / "main.yml"
    path.write_text(
        "vibe: hello\n"
        "when: {push: {}}\n"
        "the_grind:\n"
        "  build:\n"
        "    cooked_on: ubuntu-latest\n"
        "    moves:\n"
        '      - bet: echo "we are so back"\n',
        encoding="utf-8",
    )
    bag, workflow = validate_file(path, upto=4)
    assert not bag.has_errors(), [(d.code, d.message) for d in bag.errors]
    assert workflow is not None
    assert list(workflow.jobs) == ["build"]
