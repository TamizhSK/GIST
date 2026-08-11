"""Unit tests for layer4_lint rules (Dev D / Tasks D11 - D16)."""

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
                steps=[Step(pos=P0, uses="actions/checkout@main")],
            )
        },
    )
    rule = PinningRule()
    diags = rule.check(wf, wf_file)
    codes = [d.code for d in diags]
    assert "YEET-W402" in codes
    assert "YEET-W403" in codes


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
