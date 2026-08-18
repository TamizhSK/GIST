"""`yeet doctor` — the command that answers the support questions.

Its whole value is being right on a machine that is broken, which is the one
state this test suite cannot be in. So each check is driven against a forced
environment rather than against the developer's own working box.
"""

from __future__ import annotations

import sys

import pytest
import typer
from typer.testing import CliRunner

from yeet.cli import cmd_doctor
from yeet.cli.app import app

runner = CliRunner()


@pytest.fixture
def all_ok(monkeypatch):
    """A healthy machine, so a test about one failure has exactly one."""
    ok = cmd_doctor.OK
    monkeypatch.setattr(cmd_doctor, "_docker", lambda: [cmd_doctor.Check("docker", ok, "26.1")])
    monkeypatch.setattr(cmd_doctor, "_on_path", lambda: cmd_doctor.Check("path", ok, "/x"))


def test_a_healthy_machine_exits_zero(all_ok):
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "Ready" in result.output


def test_a_missing_daemon_exits_one_and_names_the_fix(monkeypatch, all_ok):
    monkeypatch.setattr(
        cmd_doctor,
        "_docker",
        lambda: [cmd_doctor.Check("docker", "fail", "no daemon", "start Docker Desktop")],
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "start Docker Desktop" in result.output


def test_the_wsl_fix_is_the_wsl_one(monkeypatch):
    """ "Docker is not running" is not an answer on a machine where the fix is
    a checkbox in Docker Desktop's WSL integration panel."""
    monkeypatch.setattr(cmd_doctor, "is_wsl", lambda: True)

    assert "WSL integration" in cmd_doctor._docker_fix()


@pytest.mark.parametrize(
    ("windows", "macos", "expected"),
    [(True, False, "winget"), (False, True, "brew"), (False, False, "apt")],
)
def test_the_python_upgrade_line_is_per_platform(monkeypatch, windows, macos, expected):
    """`python too old` is the non-answer this exists to replace."""
    monkeypatch.setattr(cmd_doctor, "is_windows", lambda: windows)
    monkeypatch.setattr(cmd_doctor, "is_macos", lambda: macos)

    assert expected in cmd_doctor._python_upgrade()


def test_an_old_python_fails_rather_than_warns(monkeypatch):
    monkeypatch.setattr(cmd_doctor.sys, "version_info", (3, 9, 6, "final", 0))

    check = cmd_doctor._python()

    assert check.status == cmd_doctor.FAIL
    assert check.fix


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="chmod cannot make a directory unwritable on Windows",
)
def test_an_unwritable_config_dir_is_reported_with_its_path(tmp_path, monkeypatch):
    """It fails much later otherwise, mid-run, as a permission error about a
    path the user never chose.

    POSIX-only, and the skip is about the SETUP rather than the check. Python's
    `os.chmod` on Windows moves one bit — FILE_ATTRIBUTE_READONLY — and that
    bit does not stop a file being created inside a directory. So `0o500` left
    the directory writable, `_writable` probed it, correctly said so, and the
    assertion below failed on the one platform where the arrangement it
    describes cannot be built.
    """
    blocked = tmp_path / "ro" / "yeet"
    blocked.parent.mkdir()
    blocked.parent.chmod(0o500)

    try:
        check = cmd_doctor._writable("config dir", blocked)
    finally:
        blocked.parent.chmod(0o700)

    assert check.status == cmd_doctor.FAIL
    assert str(blocked) in check.detail


def test_a_check_is_always_one_line():
    """`DockerUnavailable` carries a multi-line suggestion of its own, and it
    landed unindented in the middle of an aligned column."""
    check = cmd_doctor.Check("docker", "fail", "no daemon\nIs Docker Desktop running?")

    assert "\n" not in check.detail


def test_every_failing_check_carries_a_fix():
    """The rule the command exists for: a failure with no next step is the
    support ticket it was supposed to prevent."""
    for check in cmd_doctor.collect():
        if check.status == cmd_doctor.FAIL:
            assert check.fix, f"{check.name} failed with no fix"


def test_version_reports_the_four_things_an_issue_asks_for():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    for field in ("yeet ", "python ", "os ", "docker "):
        assert field in result.output, result.output


def test_the_version_banner_survives_a_dead_daemon(monkeypatch):
    """It is also what a script calls to check the tool is installed."""
    import yeet.cli.app as app_mod

    monkeypatch.setattr(app_mod, "_docker_line", lambda: "not available")

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "not available" in result.output


def test_doctor_is_in_the_help():
    """5.9 is only the highest-value item in the section if it is findable."""
    result = runner.invoke(app, ["--help"])

    assert "doctor" in result.output


def test_doctor_is_ascii(all_ok):
    """Same rule as every other command: cmd.exe renders the rest as boxes."""
    result = runner.invoke(app, ["doctor"])

    assert result.output.isascii(), result.output


def test_it_runs_from_a_bare_context(all_ok):
    """`color_enabled(ctx)` must not require the root callback to have run —
    `ctx.obj` is None when a command is invoked directly, and an AttributeError
    here would take out the one command a stuck user is told to run."""
    ctx = typer.Context(typer.main.get_command(app))

    cmd_doctor.doctor(ctx)  # healthy machine: returns rather than exiting
