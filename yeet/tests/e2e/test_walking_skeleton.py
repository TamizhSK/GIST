"""The walking skeleton (plan.md §6) — the tripwire across every seam.

This is the one test that fails if any two subsystems stop fitting together.
It drives the real CLI in a subprocess, so it exercises exactly what a user
types: analyzer -> loader -> aliases -> schema -> builder -> layer 3 -> layer 4
-> planner -> executor -> reporter, plus the exit codes and the log store.

It runs on the LOCAL backend (`cooked_on: local`), so it needs no Docker and
runs in CI on all three platforms. The Docker equivalents live in
`tests/unit/test_docker_backend.py` behind `@pytest.mark.docker`.

Why a subprocess and not `CliRunner`: exit codes and stream routing are half of
the contract here, and they are the half that a direct function call would not
check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The exact workflow printed in plan.md §6, in the yeet dialect.
WALKING_SKELETON = """\
vibe: hello
when: {push: {}}
the_grind:
  build:
    cooked_on: local
    moves:
      - bet: echo "we are so back"
"""

# The same workflow in canonical GitHub Actions syntax. plan.md §10: "the same
# workflow in standard GitHub Actions syntax also runs — superset, not
# replacement". If these two ever diverge, that claim is false.
CANONICAL = """\
name: hello
on: {push: {}}
jobs:
  build:
    runs-on: local
    steps:
      - run: echo "we are so back"
"""


def yeet(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI the way a user does."""
    env = {**os.environ, "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "yeet", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A git repo containing the walking skeleton."""
    flows = tmp_path / ".yeet" / "flows"
    flows.mkdir(parents=True)
    (flows / "main.yml").write_text(WALKING_SKELETON, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)
    return tmp_path


def test_the_walking_skeleton_runs(project: Path) -> None:
    """plan.md §6: `yeet run` exits 0 and prints that string."""
    result = yeet("run", cwd=project)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "we are so back" in combined


def test_the_dialect_passes_its_own_validator(project: Path) -> None:
    """The regression that motivated all of this.

    `vibe`/`when`/`the_grind`/`moves`/`bet` used to produce five errors from
    `yeet check` — three E201 "unknown key" plus two E202 — because
    `aliases.normalize()` had no call site in the pipeline. The tool rejected
    the workflow printed in its own plan.
    """
    result = yeet("check", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "E201" not in result.stdout


def test_canonical_github_actions_syntax_also_runs(tmp_path: Path) -> None:
    """Superset, not replacement — plan.md §10."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(CANONICAL, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)

    result = yeet("run", cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "we are so back" in combined


def test_a_broken_workflow_is_refused_before_anything_runs(tmp_path: Path) -> None:
    """plan.md §10: `yeet run` on a broken file refuses, non-zero exit.

    `needs:` pointing at a job that does not exist is E301 — semantic, so it
    proves the gate holds at layer 3 and not merely at "is this valid YAML".
    """
    flows = tmp_path / ".yeet" / "flows"
    flows.mkdir(parents=True)
    (flows / "main.yml").write_text(
        "vibe: broken\n"
        "when: {push: {}}\n"
        "the_grind:\n"
        "  build:\n"
        "    cooked_on: local\n"
        "    after: [ghost]\n"
        "    moves:\n"
        "      - bet: echo nope\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)

    result = yeet("run", cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode == 2, combined  # EXIT_BAD_WORKFLOW
    assert "E301" in combined
    assert "nope" not in result.stdout  # nothing executed


def test_a_failing_step_flops_with_a_nonzero_exit(tmp_path: Path) -> None:
    flows = tmp_path / ".yeet" / "flows"
    flows.mkdir(parents=True)
    (flows / "main.yml").write_text(
        "vibe: red\n"
        "when: {push: {}}\n"
        "the_grind:\n"
        "  build:\n"
        "    cooked_on: local\n"
        "    moves:\n"
        "      - bet: exit 3\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)

    result = yeet("run", cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr  # EXIT_JOB_FAILED


def test_a_run_is_recorded_and_replayable(project: Path) -> None:
    """`yeet logs` had nothing to replay: nothing ever constructed a RunStore.

    The JSONL is also the log format's only real test — plan.md D24's point is
    that every use of `logs` exercises it.
    """
    assert yeet("run", cwd=project).returncode == 0

    runs = list((project / ".yeet" / "runs").iterdir())
    assert len(runs) == 1, "a run must leave exactly one log directory"

    lines = (runs[0] / "log.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    assert records, "the run wrote no log events"
    assert {"ts", "job", "step", "stream", "text"} <= set(records[0])
    assert any("we are so back" in r["text"] for r in records)

    replay = yeet("logs", cwd=project)
    assert replay.returncode == 0
    assert "we are so back" in replay.stdout


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="the step body is bash (`${#VAR}`, `printf | base64`) and `local` means "
    "PowerShell on Windows; masking plumbing is unit-covered in test_masking/test_local_backend",
)
def test_a_secret_resolves_and_is_masked(tmp_path: Path) -> None:
    """Both halves, because either one alone looks like success.

    `Contexts.secrets` was never populated, so `${{ secrets.X }}` evaluated to
    an empty string. The log showed no secret — which is indistinguishable from
    perfect masking until you notice the step got nothing. This asserts the
    value ARRIVES (the step can use it) and that neither it nor its base64
    form appears in the output.
    """
    secret = "sup3rs3cr3tvalue"
    flows = tmp_path / ".yeet" / "flows"
    flows.mkdir(parents=True)
    (flows / "main.yml").write_text(
        "vibe: masking\n"
        "when: {push: {}}\n"
        "the_grind:\n"
        "  leak:\n"
        "    cooked_on: local\n"
        "    moves:\n"
        "      - vibe: try to leak\n"
        '        bet: \'echo "len=${#NPM_TOKEN} raw=$NPM_TOKEN";'
        ' printf %s "$NPM_TOKEN" | base64\'\n'
        "        drip:\n"
        "          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)

    result = yeet("run", "--secret", f"NPM_TOKEN={secret}", cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined

    # It arrived: the step saw a value of the right length.
    assert f"len={len(secret)}" in combined, combined
    # And it never reached the terminal, in either encoding.
    assert secret not in combined
    assert "***" in combined


def test_scan_finds_the_flow(project: Path) -> None:
    result = yeet("scan", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "flows found: 1" in result.stdout
    assert "main.yml" in result.stdout


def test_graph_renders_the_dag(project: Path) -> None:
    result = yeet("graph", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "build" in result.stdout
