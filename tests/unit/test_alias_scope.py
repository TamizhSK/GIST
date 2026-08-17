"""An alias is a key only where a key is a KEY.

The dialect rewrite used to walk the whole tree. That is correct for every
position where the mapping's keys come from the GitHub Actions schema, and
wrong for every position where they are the user's own words — action inputs,
env var names, matrix variables, job IDs, job outputs. A canonical
`.github/workflows` file with `with: {when: always}` came out of the parser as
`with: {on: always}`, ran differently than it was written, and announced itself
as dialect on the way past.

That is the worst failure a local runner can have: silently green here and
different there. Hence a test per user-data position, plus a proof that the
dialect still works at every position where it is genuinely a key.
"""

from __future__ import annotations

import io
import json

import pytest
from ruamel.yaml import YAML

from yeet.parser.aliases import alias_map, find_collisions, normalize
from yeet.validation.layer2_schema import SCHEMA_FILE


def _load(text: str):
    return YAML(typ="rt").load(text)


def _dump(node) -> str:
    buf = io.StringIO()
    YAML(typ="rt").dump(node, buf)
    return buf.getvalue()


def _normalized(text: str) -> tuple[str, bool]:
    tree, used = normalize(_load(text))
    return _dump(tree), used


# --- user data at key position must survive verbatim -------------------------

CANONICAL_WITH_COLLIDING_NAMES = """\
name: ci
on: [push]
env:
  where: /opt/app
jobs:
  after:
    runs-on: ubuntu-22.04
    outputs:
      bet: ${{ steps.x.outputs.v }}
    env:
      when: never
    strategy:
      matrix:
        when: [a, b]
        include:
          - when: c
            drip: d
    steps:
      - uses: some/action@v1
        with:
          when: always
          after: build
          where: ./src
          squad: red
        env:
          patience: "30"
"""


@pytest.mark.parametrize(
    "spelling",
    ["where: /opt/app", "when: never", "when: [a, b]", "when: always", "after: build"],
)
def test_a_canonical_workflow_is_returned_byte_for_byte(spelling):
    """Every one of these is an alias LEFT-hand side sitting where the user,
    not the schema, chose the word."""
    out, _ = _normalized(CANONICAL_WITH_COLLIDING_NAMES)

    assert spelling in out


def test_a_job_id_is_not_a_key():
    out, _ = _normalized(CANONICAL_WITH_COLLIDING_NAMES)

    assert "\n  after:\n" in out, out


def test_no_dialect_means_no_dialect():
    """`used_dialect` drives the style INFO. Reporting it for a file that
    contains none is how a user learns to ignore the diagnostic."""
    _, used = _normalized(CANONICAL_WITH_COLLIDING_NAMES)

    assert used is False


def test_two_action_inputs_are_not_a_collision():
    """`find_collisions` walked the same tree the same wrong way, so it refused
    a valid workflow for spelling one key two ways when it had done nothing of
    the kind."""
    tree = _load(
        "name: ci\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: a/b@v1\n"
        "        with:\n"
        "          name: one\n"
        "          vibe: two\n"
    )

    assert find_collisions(tree) == []


def test_a_real_collision_is_still_caught():
    """The narrowing must not turn the rule off — a schema position with two
    spellings of one key is still ambiguous."""
    tree = _load("name: one\nvibe: two\njobs: {}\n")

    collisions = find_collisions(tree)

    assert [c.canonical for c in collisions] == ["name"]


# --- and the dialect still works everywhere it is a key ----------------------

DIALECT_EVERYWHERE = """\
vibe: ci
when: [push]
drip:
  NODE_ENV: production
the_grind:
  build:
    cooked_on: ubuntu-22.04
    patience: 30
    squad:
      multiverse:
        node: [18, 20]
    moves:
      - vibe: checkout
        yoink: actions/checkout@v4
      - vibe: test
        bet: pytest -q
        where: ./src
        only_if: success()
        delulu: true
"""


@pytest.mark.parametrize(
    "canonical",
    [
        "name: ci",
        "on: [push]",
        "env:",
        "jobs:",
        "runs-on: ubuntu-22.04",
        "timeout-minutes: 30",
        "strategy:",
        "matrix:",
        "steps:",
        "uses: actions/checkout@v4",
        "run: pytest -q",
        "working-directory: ./src",
        "if: success()",
        "continue-on-error: true",
    ],
)
def test_every_alias_position_still_translates(canonical):
    out, used = _normalized(DIALECT_EVERYWHERE)

    assert canonical in out, out
    assert used is True


def test_a_matrix_variable_named_for_an_alias_is_left_alone_in_dialect_too():
    """Narrowing by position, not by dialect: `multiverse:` is a key and
    `where:` under it is a variable, in the same file."""
    out, used = _normalized(
        "the_grind:\n  build:\n    squad:\n      multiverse:\n        where: [a, b]\n"
    )

    assert "matrix:" in out
    assert "where: [a, b]" in out
    assert used is True


# --- the table itself --------------------------------------------------------


def _schema_property_names() -> set[str]:
    names: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    names.update(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))
    return names


def test_no_alias_shadows_a_real_github_actions_key():
    """The one way to add an alias that cannot be caught by reading a diff.

    A dialect key that is ALSO a real key means every canonical workflow using
    it is silently rewritten, and the rewrite looks correct in the table.
    Checked against the schema so a new alias is graded against the real
    vocabulary rather than against somebody's memory of it.
    """
    shadowed = sorted(set(alias_map()) & _schema_property_names())

    assert shadowed == [], f"these aliases are real GitHub Actions keys: {shadowed}"


def test_aliases_that_share_a_target_are_caught_when_used_together():
    """The table is deliberately NOT injective — `bet` and `cook` are both
    `run`, and that is the dialect being a dialect. What must not happen is
    both in one mapping, where one silently wins."""
    by_target: dict[str, list[str]] = {}
    for alias, canonical in alias_map().items():
        by_target.setdefault(canonical, []).append(alias)
    pairs = [names for names in by_target.values() if len(names) > 1]
    assert pairs, "the point of this test is gone if the table becomes injective"

    for first, second, *_ in pairs:
        tree = _load(f"jobs:\n  build:\n    steps:\n      - {first}: a\n        {second}: b\n")
        assert find_collisions(tree), f"{first}/{second} collide and were not reported"


def test_container_and_service_positions():
    """`services:` keys are service IDs; the container mappings under them are
    schema. Two different rules one level apart."""
    out, _ = _normalized(
        "jobs:\n"
        "  build:\n"
        "    container:\n"
        "      image: node:20\n"
        "      drip:\n"
        "        when: never\n"
        "    services:\n"
        "      after:\n"
        "        image: redis\n"
    )

    assert "env:" in out, out  # container.drip -> container.env
    assert "when: never" in out  # its contents are env vars
    assert "\n      after:\n" in out  # the service ID is untouched
