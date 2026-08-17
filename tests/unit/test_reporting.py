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
from yeet.reporting.theme import BRANCH


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
    # The HEADER, not the bare name: once a run has more than one job every
    # line carries a `job |` gutter, so the name legitimately appears many
    # times. What must not repeat is the `> job [cooked]` banner.
    assert output.count("> test (node 16) [cooked]") == 1
    assert output.count("> test (node 18) [cooked]") == 1
    assert output.count("> test (node 20) [cooked]") == 1
    # One step header per job per step, still — three legs, two steps.
    assert output.count(f"{BRANCH}> run tests") == 3
    assert output.count(f"{BRANCH}> collect") == 3


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


def test_a_single_job_run_has_no_gutter() -> None:
    """The common case stays exactly as clean as it was. A prefix on every
    line of a one-job run would be pure noise — there is nothing to
    disambiguate it from."""
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False)

    console.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="hello"))

    assert "|" not in buf.getvalue()
    assert "hello" in buf.getvalue()


def test_parallel_jobs_attribute_every_line() -> None:
    """Three legs share one stream. Before the gutter, a reader got three
    identical `+-- setup` headers and then `using node 16/18/20` in whatever
    order the threads reached the sink — every line true, the block as a whole
    saying nothing."""
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False)

    for job, text in [
        ("test (node 16)", "using node 16"),
        ("test (node 18)", "using node 18"),
        ("test (node 16)", "done 16"),
    ]:
        console.emit(LogEvent.now(job=job, step="setup", stream=STDOUT, text=text))

    lines = [ln for ln in buf.getvalue().splitlines() if "using node 18" in ln]
    assert lines and lines[0].startswith("test (node 18) |"), lines


def test_one_jobs_group_does_not_indent_another(tmp_path) -> None:
    """`_group_depth` was a single shared counter while jobs emit from
    parallel threads, so one job's `::group::` shifted another job's output
    and either job's `::endgroup::` closed it."""
    buf = io.StringIO()
    console = RunConsole(out=buf, color=False, verbose=True)

    console.emit(LogEvent.now(job="a", step="s", stream=STDOUT, text="::group::deps"))
    console.emit(LogEvent.now(job="b", step="s", stream=STDOUT, text="plain"))

    line = next(ln for ln in buf.getvalue().splitlines() if ln.endswith("plain"))
    body = line.split("|", 1)[1] if "|" in line else line
    assert body == "     plain", f"job b must keep its own indent, got {body!r}"
