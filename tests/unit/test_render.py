"""Unit tests for reporting/render.py code-frame renderer (Dev D / Task D5)."""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.reporting.render import render_diagnostics


def test_render_empty_bag() -> None:
    bag = DiagnosticBag()
    assert render_diagnostics(bag) == ""


def test_render_basic_diagnostic_without_file() -> None:
    diag = Diagnostic(
        code="YEET-E101",
        severity=Severity.ERROR,
        message="Workflow syntax invalid",
    )
    bag = DiagnosticBag([diag])
    rendered = render_diagnostics(bag, color=False)
    assert "error[YEET-E101]: Workflow syntax invalid" in rendered


def test_render_code_frame_with_file(tmp_path: Path) -> None:
    sample_yaml = tmp_path / "workflow.yml"
    sample_yaml.write_text(
        "name: CI\non: push\njobs:\n  build:\n    needs: [bad_job]\n", encoding="utf-8"
    )

    diag = Diagnostic(
        code="YEET-E301",
        severity=Severity.ERROR,
        message="Job `build` references unknown dependency `bad_job`",
        file=sample_yaml,
        pos=Position(line=4, col=11, end_col=20),
        help="Did you mean `test`?",
    )
    bag = DiagnosticBag([diag])
    rendered = render_diagnostics(bag, color=False)

    assert "error[YEET-E301]" in rendered
    assert "workflow.yml:5:12" in rendered
    assert "needs: [bad_job]" in rendered
    assert "^^^^^^^^^" in rendered
    assert "= help: Did you mean `test`?" in rendered


def test_render_handles_out_of_bounds_positions(tmp_path: Path) -> None:
    sample_yaml = tmp_path / "empty.yml"
    sample_yaml.write_text("short\n", encoding="utf-8")

    diag = Diagnostic(
        code="YEET-E999",
        severity=Severity.WARNING,
        message="Out of bounds test",
        file=sample_yaml,
        pos=Position(line=9999, col=-50),
    )
    bag = DiagnosticBag([diag])

    # Must never crash, must return readable text
    rendered = render_diagnostics(bag, color=False)
    assert "warning[YEET-E999]: Out of bounds test" in rendered
