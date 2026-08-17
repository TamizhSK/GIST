"""Where a workflow may live, and which spelling it may be written in.

Two independent axes that kept getting confused for one:

* **Layout.** `.github/workflows/` and `.yeet/flows/` used to be matched only
  as exactly three root-relative path segments, so a monorepo package's own
  `.github/workflows/ci.yml` and a nested `.github/workflows/reusable/x.yml`
  were both invisible — `yeet scan` reported "no flows found" on a repo the
  user could see workflows in. A bare `workflows/` directory was never
  recognised at all.

* **Dialect.** Canonical GitHub Actions syntax and the yeet dialect are both
  accepted in EVERY file in EVERY directory. Nothing keys off the path: a
  dialect file under `.github/workflows/` runs, and a stock GitHub workflow
  copied into `.yeet/flows/` runs. The tests below assert the cross product,
  because "it works in the directory we happened to test" is the failure this
  file exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.analyzer.discover import discover
from yeet.validation.pipeline import validate_file

CANONICAL = """\
name: canonical
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: greet
        run: echo hello
"""

DIALECT = """\
vibe: dialect
when: [push]
the_grind:
  build:
    cooked_on: ubuntu-latest
    moves:
      - vibe: greet
        bet: echo hello
"""


def _touch(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _rels(root: Path) -> list[str]:
    return [f.relative_to(root).as_posix() for f in discover(root).flows]


# --- layout -----------------------------------------------------------------


def test_a_monorepo_package_has_its_own_github_workflows(tmp_path):
    """The bug in one line: this returned [] before."""
    root = tmp_path / "mono"
    _touch(root / ".git" / "HEAD", "ref: refs/heads/main\n")
    _touch(root / ".github" / "workflows" / "root.yml", CANONICAL)
    _touch(root / "packages" / "api" / ".github" / "workflows" / "ci.yml", CANONICAL)
    _touch(root / "packages" / "web" / ".github" / "workflows" / "ci.yaml", CANONICAL)

    assert _rels(root) == [
        ".github/workflows/root.yml",
        "packages/api/.github/workflows/ci.yml",
        "packages/web/.github/workflows/ci.yaml",
    ]


def test_subdirectories_inside_a_workflow_directory_are_walked(tmp_path):
    """`.github/workflows/reusable/build.yml` is a real layout GitHub allows."""
    root = tmp_path / "nested"
    _touch(root / ".github" / "workflows" / "ci.yml", CANONICAL)
    _touch(root / ".github" / "workflows" / "reusable" / "build.yml", CANONICAL)

    assert _rels(root) == [
        ".github/workflows/ci.yml",
        ".github/workflows/reusable/build.yml",
    ]


def test_a_bare_workflows_directory_counts(tmp_path):
    root = tmp_path / "bare"
    _touch(root / "workflows" / "ci.yml", CANONICAL)
    _touch(root / "ci" / "workflows" / "nightly.yaml", CANONICAL)

    assert _rels(root) == ["workflows/ci.yml", "ci/workflows/nightly.yaml"]


def test_precedence_runs_yeet_then_github_then_bare_then_root(tmp_path):
    root = tmp_path / "all"
    _touch(root / "yeet.yml", CANONICAL)
    _touch(root / "workflows" / "bare.yml", CANONICAL)
    _touch(root / ".github" / "workflows" / "gh.yml", CANONICAL)
    _touch(root / ".yeet" / "flows" / "main.yml", CANONICAL)

    assert _rels(root) == [
        ".yeet/flows/main.yml",
        ".github/workflows/gh.yml",
        "workflows/bare.yml",
        "yeet.yml",
    ]


def test_within_one_rank_the_shallowest_wins(tmp_path):
    """`yeet run` with no `--flow` takes flows[0]; the repo's own workflow is a
    better default than a vendored example three directories down."""
    root = tmp_path / "tie"
    _touch(root / "examples" / "demo" / ".github" / "workflows" / "aaa.yml", CANONICAL)
    _touch(root / ".github" / "workflows" / "zzz.yml", CANONICAL)

    assert _rels(root)[0] == ".github/workflows/zzz.yml"


def test_pointing_yeet_straight_at_a_workflows_directory_works(tmp_path):
    """`cd .github/workflows && yeet scan` — the directory IS the root here, so
    the match has to be made against its own name, not a relative path."""
    root = tmp_path / "repo" / ".github" / "workflows"
    _touch(root / "ci.yml", CANONICAL)

    assert _rels(root) == ["ci.yml"]


def test_a_workflows_directory_ABOVE_the_root_does_not_capture_the_project(tmp_path):
    """A project that happens to live under `~/workflows/` is not one big
    workflow directory. Ancestor matching stops at the root."""
    root = tmp_path / "workflows" / "myrepo"
    _touch(root / ".git" / "HEAD", "ref: refs/heads/main\n")
    _touch(root / "config" / "settings.yml", "a: 1\n")
    _touch(root / "docker-compose.yaml", "services: {}\n")

    assert _rels(root) == []


def test_a_nested_yeet_runtime_directory_is_not_scanned(tmp_path):
    """`.yeet/runs/` holds a run's own logs. A sub-package's copy is just as
    uninteresting as the root one, and the old root-relative spelling missed
    it."""
    root = tmp_path / "runtime"
    _touch(root / ".yeet" / "flows" / "main.yml", CANONICAL)
    _touch(root / "packages" / "api" / ".yeet" / "runs" / "run-1" / "log.yml", CANONICAL)
    _touch(root / "packages" / "api" / ".yeet" / "flows" / "api.yml", CANONICAL)

    assert _rels(root) == [
        ".yeet/flows/main.yml",
        "packages/api/.yeet/flows/api.yml",
    ]


def test_each_flow_reports_where_it_came_from(tmp_path):
    root = tmp_path / "sources"
    _touch(root / ".yeet" / "flows" / "main.yml", CANONICAL)
    _touch(root / ".github" / "workflows" / "gh.yml", CANONICAL)
    _touch(root / "workflows" / "bare.yml", CANONICAL)
    _touch(root / "yeet.yml", CANONICAL)

    found = discover(root)
    labels = {p.name: found.sources[p] for p in found.flows}
    assert labels == {
        "main.yml": "yeet",
        "gh.yml": "github",
        "bare.yml": "workflows",
        "yeet.yml": "root",
    }


def test_foreign_ci_is_still_reported_not_parsed(tmp_path):
    root = tmp_path / "foreign"
    _touch(root / ".gitlab-ci.yml", "stages: []\n")
    _touch(root / "workflows" / "ci.yml", CANONICAL)

    found = discover(root)
    assert [f.name for f in found.foreign_ci] == [".gitlab-ci.yml"]
    assert [f.name for f in found.flows] == ["ci.yml"]


# --- dialect, in every location ---------------------------------------------


@pytest.mark.parametrize(
    "where",
    [".github/workflows", ".yeet/flows", "workflows", "packages/api/.github/workflows"],
)
@pytest.mark.parametrize("source", [CANONICAL, DIALECT], ids=["canonical", "dialect"])
def test_both_spellings_validate_from_any_directory(tmp_path, where, source):
    """The cross product. Nothing about parsing may depend on the path."""
    root = tmp_path / "cross"
    flow = _touch(root / where / "flow.yml", source)

    assert _rels(root) == f"{where}/flow.yml".split("\n")

    bag, workflow = validate_file(flow, upto=4)
    assert [str(d) for d in bag.items] == []
    assert workflow is not None
    assert workflow.jobs["build"].steps[0].run == "echo hello"


def test_a_dialect_and_a_canonical_flow_build_the_same_job(tmp_path):
    root = tmp_path / "parity"
    gh = _touch(root / ".github" / "workflows" / "canonical.yml", CANONICAL)
    yt = _touch(root / ".yeet" / "flows" / "dialect.yml", DIALECT)

    _, a = validate_file(gh, upto=3)
    _, b = validate_file(yt, upto=3)

    assert a is not None and b is not None
    assert a.jobs.keys() == b.jobs.keys()
    assert a.jobs["build"].runs_on == b.jobs["build"].runs_on
    assert [s.run for s in a.jobs["build"].steps] == [s.run for s in b.jobs["build"].steps]
    assert a.used_dialect is False
    assert b.used_dialect is True


def test_one_file_may_mix_the_two_spellings(tmp_path):
    """Half-and-half is legal — people migrate a file a key at a time."""
    flow = _touch(
        tmp_path / "blend" / ".github" / "workflows" / "mix.yml",
        "name: half and half\n"
        "on: [push]\n"
        "the_grind:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    moves:\n"
        "      - name: canonical step\n"
        "        run: echo one\n"
        "      - vibe: dialect step\n"
        "        bet: echo two\n",
    )

    bag, workflow = validate_file(flow, upto=4)
    assert [str(d) for d in bag.items] == []
    assert workflow is not None
    assert workflow.name == "half and half"
    assert [s.name for s in workflow.jobs["build"].steps] == ["canonical step", "dialect step"]


def test_the_same_key_in_both_spellings_is_refused(tmp_path):
    """E106. The alias rewrite is a pop-and-reinsert, so before this check the
    `name:` here was dropped without a word and the run used `vibe:`."""
    flow = _touch(
        tmp_path / "clash" / "workflows" / "clash.yml",
        "name: canonical name\nvibe: dialect name\non: [push]\njobs:\n"
        "  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
    )

    bag, workflow = validate_file(flow, upto=3)
    assert [d.code for d in bag.items] == ["YEET-E106"]
    assert workflow is None
    assert bag.items[0].pos is not None
    assert bag.items[0].pos.line == 1  # points at `vibe:`, the one that wins


def test_two_dialect_spellings_of_one_key_also_clash(tmp_path):
    """`bet:` and `cook:` are both `run:`."""
    flow = _touch(
        tmp_path / "clash2" / "workflows" / "c.yml",
        "vibe: x\nwhen: [push]\nthe_grind:\n  build:\n    cooked_on: ubuntu-latest\n"
        "    moves:\n      - bet: echo one\n        cook: echo two\n",
    )

    bag, _ = validate_file(flow, upto=3)
    assert [d.code for d in bag.items] == ["YEET-E106"]
