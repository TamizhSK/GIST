"""`yeet run`'s gate: errors stop it, warnings no longer bury the run.

Layer 4 still runs and still never blocks — only where it is DISPLAYED changed.
`yeet run` is the command you type to watch your build, not to read a lint
report, and `yeet check` already prints every warning with its code frame.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from yeet.cli.cmd_run import _gate
from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity

P0 = Position(0, 0)


def _bag(*items: Diagnostic) -> DiagnosticBag:
    bag = DiagnosticBag()
    for item in items:
        bag.add(item)
    return bag


def _warning(code: str = "YEET-W405") -> Diagnostic:
    return Diagnostic(
        code=code, severity=Severity.WARNING, message="a warning", file=Path("f.yml"), pos=P0
    )


def _error(code: str = "YEET-E301") -> Diagnostic:
    return Diagnostic(
        code=code, severity=Severity.ERROR, message="an error", file=Path("f.yml"), pos=P0
    )


def test_warnings_are_summarised_to_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    _gate(_bag(_warning(), _warning("YEET-W401")), Path("f.yml"))
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "2 warning(s)" in err
    assert "YEET-W401, YEET-W405" in err
    assert "yeet check" in err


def test_the_summary_never_prints_a_code_frame(capsys: pytest.CaptureFixture[str]) -> None:
    """The whole point: a screenful of layer 4 before every run buries the
    output the user actually asked for."""
    _gate(_bag(_warning()), Path("f.yml"))
    err = capsys.readouterr().err
    assert "help:" not in err
    assert "-->" not in err


def test_verbose_prints_them_in_full(capsys: pytest.CaptureFixture[str]) -> None:
    _gate(_bag(_warning()), Path("f.yml"), verbose=True)
    err = capsys.readouterr().err
    assert "YEET-W405" in err
    assert "warning(s)" not in err  # the full render, not the summary


def test_a_clean_workflow_says_nothing_at_all(capsys: pytest.CaptureFixture[str]) -> None:
    _gate(_bag(), Path("f.yml"))
    assert capsys.readouterr().err == ""


def test_errors_still_stop_the_run_and_are_rendered_in_full(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The gate is the product's safety claim; only the warning half moved."""
    with pytest.raises(typer.Exit) as caught:
        _gate(_bag(_error(), _warning()), Path("f.yml"))
    assert caught.value.exit_code == 2
    err = capsys.readouterr().err
    assert "YEET-E301" in err
    assert "refusing to run" in err


def test_an_error_takes_the_warnings_with_it(capsys: pytest.CaptureFixture[str]) -> None:
    """When the run is stopping anyway, everything is worth showing at once."""
    with pytest.raises(typer.Exit):
        _gate(_bag(_error(), _warning()), Path("f.yml"))
    assert "YEET-W405" in capsys.readouterr().err
