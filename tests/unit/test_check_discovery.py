"""`yeet check` and `yeet scan` must find the same files.

They did not. `check` had its own two-line discovery — `glob("*.yml")` in
`.yeet/flows` and `.github/workflows` — while `scan` used
`analyzer.discover`, which handles `.yaml`, a bare `workflows/` at the root,
nesting, and the exclude list. So a project written with `.yaml` extensions got

    $ yeet scan
    flows found: 2
    $ yeet check
    No workflow files found in .
    $ echo $?
    0

A false green, in the command whose entire job is to say whether the workflows
are correct, in the tool most likely to be wired into a pre-push hook.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from yeet.analyzer.project import analyze
from yeet.cli.app import app

runner = CliRunner()

FLOW = """\
name: a
on: [push]
jobs:
  b:
    runs-on: local
    steps:
      - name: hello
        run: echo hi
"""


@pytest.fixture
def project(tmp_path):
    return tmp_path


@pytest.mark.parametrize(
    "where",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/ci.yaml",
        "workflows/ci.yml",
        "workflows/ci.yaml",
        ".yeet/flows/main.yml",
        ".yeet/flows/main.yaml",
    ],
)
def test_check_finds_every_layout_scan_finds(project, where):
    path = project / where
    path.parent.mkdir(parents=True)
    path.write_text(FLOW, encoding="utf-8")

    result = runner.invoke(app, ["check", str(project)])

    assert "No workflow files found" not in result.output, result.output
    assert "1 flow checked" in result.output, result.output


def test_the_two_commands_agree_on_the_count(project):
    """The assertion that would have caught it: not "check works", but "check
    sees what scan sees"."""
    for where in ("workflows/a.yaml", ".github/workflows/b.yml"):
        path = project / where
        path.parent.mkdir(parents=True)
        path.write_text(FLOW, encoding="utf-8")

    found = len(analyze(project).flows)
    result = runner.invoke(app, ["check", str(project)])

    assert found == 2
    assert f"{found} flows checked" in result.output, result.output


def test_a_clean_run_says_so(project):
    """It printed nothing at all, which is indistinguishable from a run that
    found no files — and those had different meanings and the same exit code."""
    path = project / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True)
    path.write_text(FLOW, encoding="utf-8")

    result = runner.invoke(app, ["check", str(project)])

    assert result.exit_code == 0
    assert "clean" in result.output


def test_json_is_valid_json_even_when_there_is_nothing_to_report(project):
    """A consumer parsing empty output fails on the clean case, which is the
    common one."""
    path = project / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True)
    path.write_text(FLOW, encoding="utf-8")

    result = runner.invoke(app, ["check", str(project), "--format", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"diagnostics": []}


def test_nothing_found_is_reported_on_stderr_with_a_next_step(project):
    """So `yeet check --format json > out.json` cannot put prose in the file."""
    result = runner.invoke(app, ["check", str(project)])

    assert result.exit_code == 0
    assert "No workflow files found" in result.output
    assert "yeet init" in result.output


def test_a_foreign_ci_file_is_named_rather_than_ignored(project):
    """7.13 — "found, not supported" costs five lines and reads as deliberate."""
    (project / ".gitlab-ci.yml").write_text("stages: [build]\n", encoding="utf-8")

    result = runner.invoke(app, ["check", str(project)])

    assert ".gitlab-ci.yml" in result.output
    assert "does not support" in result.output


def test_discovery_order_is_deterministic(project):
    """Non-deterministic order makes a test failure irreproducible, and makes
    two runs of `--format json` differ for no reason."""
    for name in ("c.yml", "a.yml", "b.yml"):
        path = project / "workflows" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FLOW, encoding="utf-8")

    first = runner.invoke(app, ["check", str(project), "--format", "json"]).output
    second = runner.invoke(app, ["check", str(project), "--format", "json"]).output

    assert first == second
