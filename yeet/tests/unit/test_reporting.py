"""Unit tests for reporting/console.py, json_out.py, and sarif.py (Dev D / Tasks D6 & D7)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.events import META, STDERR, STDOUT, LogEvent
from yeet.reporting.console import RunConsole
from yeet.reporting.json_out import to_json
from yeet.reporting.sarif import to_sarif


def test_run_console_emit() -> None:
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False)

    console.emit(LogEvent.now(job="build", step="setup", stream=META, text="Initializing runner"))
    console.emit(
        LogEvent.now(job="build", step="compile", stream=STDOUT, text="Compiling sources...")
    )
    console.emit(
        LogEvent.now(job="build", step="compile", stream=STDERR, text="Warning: unused variable")
    )

    output = buf.getvalue()
    assert "build" in output
    assert "Initializing runner" in output
    assert "Compiling sources..." in output
    assert "Warning: unused variable" in output


def test_run_console_group_directives() -> None:
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False)

    console.emit(
        LogEvent.now(job="build", step="setup", stream=META, text="::group::Environment Info")
    )
    console.emit(LogEvent.now(job="build", step="setup", stream=STDOUT, text="OS: Ubuntu 22.04"))
    console.emit(LogEvent.now(job="build", step="setup", stream=META, text="::endgroup::"))

    output = buf.getvalue()
    assert "Environment Info" in output
    assert "OS: Ubuntu 22.04" in output


def test_matrix_legs_each_print_one_header_when_interleaved() -> None:
    """Parallel matrix legs interleave their events; a job must print its
    header once, not once per burst (the session-5 double-rendering bug)."""
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False)

    for job, step in [
        ("test (node 16)", "run tests"),
        ("test (node 18)", "run tests"),
        ("test (node 20)", "run tests"),
        ("test (node 16)", "collect"),
        ("test (node 18)", "collect"),
        ("test (node 20)", "collect"),
    ]:
        console.emit(LogEvent.now(job=job, step=step, stream=STDOUT, text="line"))

    output = buf.getvalue()
    assert output.count("test (node 16)") == 1
    assert output.count("test (node 18)") == 1
    assert output.count("test (node 20)") == 1
    assert output.count("run tests") == 3
    assert output.count("collect") == 3


def test_to_json_exporter(tmp_path: Path) -> None:
    diag_file = tmp_path / "test.yml"
    diag = Diagnostic(
        code="YEET-E201",
        severity=Severity.ERROR,
        message="Unknown key `foo`",
        file=diag_file,
        pos=Position(line=2, col=4),
        help="Remove `foo`",
    )
    bag = DiagnosticBag([diag])
    json_str = to_json(bag)
    data = json.loads(json_str)

    assert "diagnostics" in data
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["code"] == "YEET-E201"
    assert data["diagnostics"][0]["line"] == 3
    assert data["diagnostics"][0]["col"] == 5


def test_to_sarif_exporter(tmp_path: Path) -> None:
    diag_file = tmp_path / "test.yml"
    diag = Diagnostic(
        code="YEET-W401",
        severity=Severity.WARNING,
        message="Workflow has no name",
        file=diag_file,
        pos=Position(line=0, col=0),
    )
    bag = DiagnosticBag([diag])
    sarif_str = to_sarif(bag)
    data = json.loads(sarif_str)

    assert data["version"] == "2.1.0"
    assert len(data["runs"]) == 1
    results = data["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "YEET-W401"
    assert results[0]["level"] == "warning"
