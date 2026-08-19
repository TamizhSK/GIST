"""Unit tests for layer4_lint rules (Dev D / Tasks D11 - D16).

NOTE the import style below: the rule classes are imported directly, which is
convenient for testing one rule in isolation and is *exactly* how this file hid
a production bug for three sessions. Rules self-register on import, so
importing `NamingRule` here registered it here — while the product imported
only `layer4_lint.base` and ran with `RULES == []`, i.e. no lints at all.

`test_registration.py` is the guard for that; keep these direct imports for the
per-rule tests, but never treat them as evidence the layer is wired up.
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Position
from yeet.core.ir import Job, Step, Workflow
from yeet.validation.layer4_lint.base import run_lints
from yeet.validation.layer4_lint.naming import NamingRule
from yeet.validation.layer4_lint.pinning import PinningRule
from yeet.validation.layer4_lint.secrets_scan import SecretsScanRule

P0 = Position(0, 0)


def test_naming_rule(tmp_path: Path) -> None:
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="",
        jobs={
            "build": Job(
                key="build", pos=P0, name="build", steps=[Step(pos=P0, name="", run="echo hi")]
            )
        },
    )
    rule = NamingRule()
    diags = rule.check(wf, wf_file)
    codes = [d.code for d in diags]
    assert "YEET-W401" in codes


def test_pinning_rule(tmp_path: Path) -> None:
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="CI",
        jobs={
            "build": Job(
                key="build",
                pos=P0,
                name="build",
                runs_on="ubuntu-latest",
                container_image="node:latest",
                steps=[Step(pos=P0, uses="actions/checkout@main")],
            )
        },
    )
    rule = PinningRule()
    diags = rule.check(wf, wf_file)
    codes = [d.code for d in diags]
    assert "YEET-W402" in codes  # uses: ...@main
    assert "YEET-W403" in codes  # container: node:latest


def test_w403_ignores_the_runner_label(tmp_path: Path) -> None:
    """`runs-on: ubuntu-latest` is a runner label, not a floating image tag.

    W403 used to fire on it, which meant the rule went off on plan.md's own
    walking skeleton and on essentially every real workflow. A lint that cries
    wolf on the recommended spelling gets the whole layer switched off.
    """
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="CI",
        jobs={
            "build": Job(
                key="build",
                pos=P0,
                name="build",
                runs_on="ubuntu-latest",  # the only "latest" in this workflow
                steps=[Step(pos=P0, uses="actions/checkout@a1b2c3d")],
            )
        },
    )
    diags = PinningRule().check(wf, wf_file)
    assert [d.code for d in diags] == []


def test_w403_flags_an_untagged_image(tmp_path: Path) -> None:
    """No tag at all resolves to :latest, so it floats just the same."""
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="CI",
        jobs={"build": Job(key="build", pos=P0, name="build", container_image="python", steps=[])},
    )
    assert "YEET-W403" in [d.code for d in PinningRule().check(wf, wf_file)]


def test_w403_accepts_a_pinned_image(tmp_path: Path) -> None:
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="CI",
        jobs={
            "build": Job(
                key="build",
                pos=P0,
                name="build",
                container_image="ghcr.io/acme/python:3.12",
                steps=[],
            )
        },
    )
    assert [d.code for d in PinningRule().check(wf, wf_file)] == []


def test_secrets_scan_rule(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.yml"
    secret_file.write_text("env:\n  AWS: AKIA1234567890ABCDEF\n", encoding="utf-8")
    wf = Workflow(source=secret_file, pos=P0, name="CI", jobs={})
    rule = SecretsScanRule()
    diags = rule.check(wf, secret_file)
    codes = [d.code for d in diags]
    assert "YEET-W404" in codes


def test_run_lints_with_override(tmp_path: Path) -> None:
    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="",
        jobs={"build": Job(key="build", pos=P0, name="build", steps=[Step(pos=P0, run="echo hi")])},
    )
    cfg = {"YEET-W401": "off"}
    bag = run_lints(wf, wf_file, cfg)
    codes = [d.code for d in bag.items]
    assert "YEET-W401" not in codes


# --- W405: `set -euo pipefail` is bash, and only bash ---------------------------


MULTILINE = "echo one\necho two\necho three"


def _shell_diags(tmp_path: Path, *, shell: str | None = None, defaults: dict | None = None):
    from yeet.validation.layer4_lint.shell import ShellRule

    wf_file = tmp_path / "test.yml"
    wf = Workflow(
        source=wf_file,
        pos=P0,
        name="w",
        jobs={
            "build": Job(
                key="build",
                pos=P0,
                name="build",
                steps=[Step(pos=P0, name="s", run=MULTILINE, shell=shell)],
            )
        },
        defaults=defaults or {},
    )
    return [d.code for d in ShellRule().check(wf, wf_file)]


def test_w405_fires_on_a_plain_multiline_run(tmp_path: Path) -> None:
    """The case the rule was written for: no `shell:`, so bash in a container."""
    assert "YEET-W405" in _shell_diags(tmp_path)


def test_w405_fires_on_an_explicit_posix_shell(tmp_path: Path) -> None:
    for shell in ("bash", "sh"):
        assert "YEET-W405" in _shell_diags(tmp_path, shell=shell), shell


def test_w405_is_silent_on_shells_where_the_advice_would_break_the_step(
    tmp_path: Path,
) -> None:
    """`set -euo pipefail` is a bash builtin. Telling a pwsh, python, node or
    cmd step to put it at the top is advice that breaks the step if followed —
    and it fired on exactly the cross-platform workflows that need most help."""
    for shell in ("pwsh", "powershell", "python", "node", "cmd"):
        assert "YEET-W405" not in _shell_diags(tmp_path, shell=shell), shell


def test_w405_respects_a_shell_that_is_already_safe(tmp_path: Path) -> None:
    """`shell: bash -eo pipefail {0}` is GitHub's own spelling of "already done"."""
    assert "YEET-W405" not in _shell_diags(tmp_path, shell="bash -eo pipefail {0}")


def test_w405_reads_workflow_level_defaults(tmp_path: Path) -> None:
    """`defaults: {run: {shell: pwsh}}` at the top applies to every step under it."""
    defaults = {"run": {"shell": "pwsh"}}
    assert "YEET-W405" not in _shell_diags(tmp_path, defaults=defaults)
    assert "YEET-W405" in _shell_diags(tmp_path, defaults={"run": {"shell": "bash"}})


def test_a_step_shell_beats_the_workflow_default(tmp_path: Path) -> None:
    assert "YEET-W405" in _shell_diags(tmp_path, shell="bash", defaults={"run": {"shell": "pwsh"}})
