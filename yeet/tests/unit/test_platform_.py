"""C2 — OS detection. Every branch is forced, so CI's Linux runner tests all three."""

from __future__ import annotations

import pytest

from yeet.executor import platform_


@pytest.mark.parametrize(
    ("sys_platform", "windows", "macos", "linux"),
    [
        ("win32", True, False, False),
        ("darwin", False, True, False),
        ("linux", False, False, True),
    ],
)
def test_os_detection(monkeypatch, sys_platform, windows, macos, linux):
    monkeypatch.setattr(platform_.sys, "platform", sys_platform)
    assert platform_.is_windows() is windows
    assert platform_.is_macos() is macos
    assert platform_.is_linux() is linux


def test_is_wsl_reads_proc_version(monkeypatch, tmp_path):
    proc = tmp_path / "version"
    proc.write_text("Linux version 5.15.0-microsoft-standard-WSL2")
    monkeypatch.setattr(platform_.sys, "platform", "linux")
    monkeypatch.setattr(platform_, "PROC_VERSION", proc)
    assert platform_.is_wsl() is True


def test_is_wsl_false_on_plain_linux(monkeypatch, tmp_path):
    proc = tmp_path / "version"
    proc.write_text("Linux version 6.1.0-generic")
    monkeypatch.setattr(platform_.sys, "platform", "linux")
    monkeypatch.setattr(platform_, "PROC_VERSION", proc)
    assert platform_.is_wsl() is False


def test_is_wsl_survives_a_missing_proc(monkeypatch, tmp_path):
    """It sits in the container setup path — an unreadable /proc is not fatal."""
    monkeypatch.setattr(platform_.sys, "platform", "linux")
    monkeypatch.setattr(platform_, "PROC_VERSION", tmp_path / "nope")
    assert platform_.is_wsl() is False


def test_is_wsl_false_off_linux(monkeypatch):
    monkeypatch.setattr(platform_.sys, "platform", "darwin")
    assert platform_.is_wsl() is False


def test_docker_user_is_none_on_docker_desktop(monkeypatch):
    """Risk #6. Passing a host uid to Docker Desktop breaks the container."""
    for sys_platform in ("darwin", "win32"):
        monkeypatch.setattr(platform_.sys, "platform", sys_platform)
        assert platform_.docker_user() is None


def test_docker_user_is_uid_gid_on_linux(monkeypatch):
    monkeypatch.setattr(platform_.sys, "platform", "linux")
    monkeypatch.setattr(platform_.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(platform_.os, "getgid", lambda: 1000, raising=False)
    assert platform_.docker_user() == "1000:1000"


def test_runner_os_vocabulary(monkeypatch):
    for sys_platform, expected in (("win32", "Windows"), ("darwin", "macOS"), ("linux", "Linux")):
        monkeypatch.setattr(platform_.sys, "platform", sys_platform)
        assert platform_.runner_os() == expected


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("x86_64", "X64"), ("AMD64", "X64"), ("arm64", "ARM64"), ("aarch64", "ARM64")],
)
def test_runner_arch(monkeypatch, machine, expected):
    monkeypatch.setattr(platform_.platform, "machine", lambda: machine)
    assert platform_.runner_arch() == expected


def test_docker_hint_is_platform_specific(monkeypatch):
    monkeypatch.setattr(platform_.sys, "platform", "darwin")
    assert "Docker Desktop" in platform_.docker_host_hint()

    monkeypatch.setattr(platform_.sys, "platform", "linux")
    monkeypatch.setattr(platform_, "is_wsl", lambda: False)
    assert "systemctl" in platform_.docker_host_hint()

    monkeypatch.setattr(platform_, "is_wsl", lambda: True)
    assert "WSL" in platform_.docker_host_hint()


def test_bash_on_windows_is_git_bash_not_the_wsl_launcher(monkeypatch, tmp_path):
    """`bash` on a stock Windows box is `C:\\Windows\\System32\\bash.exe`.

    That is the WSL launcher, not a shell. With no distribution installed it
    prints "Windows Subsystem for Linux has no installed distributions" — in
    UTF-16 — and exits non-zero, so a `shell: bash` step fails with a message
    about Linux distributions that has nothing to do with the workflow. This is
    what reddened windows-latest after the `.ps1` fix landed.
    """
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_text("")

    monkeypatch.setattr(platform_, "is_windows", lambda: True)
    monkeypatch.setattr(platform_, "GIT_BASH_CANDIDATES", (str(git_bash),))

    assert platform_.shell_executable("bash") == str(git_bash)
    assert platform_.shell_executable("sh") == str(git_bash)


def test_shell_executable_only_rewrites_posix_shells_on_windows(monkeypatch):
    monkeypatch.setattr(platform_, "is_windows", lambda: True)
    monkeypatch.setattr(platform_, "GIT_BASH_CANDIDATES", ())
    monkeypatch.setattr(platform_.shutil, "which", lambda _name: None)

    # pwsh is a real program on Windows and must be left alone.
    assert platform_.shell_executable("pwsh") == "pwsh"
    # No Git Bash anywhere: return the bare name so the failure is the user's
    # PATH rather than a path we invented.
    assert platform_.shell_executable("bash") == "bash"


def test_shell_executable_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(platform_, "is_windows", lambda: False)
    assert platform_.shell_executable("bash") == "bash"
    assert platform_.shell_executable("sh") == "sh"


def test_pid_alive_says_yes_to_us_and_no_to_a_fiction():
    import os

    assert platform_.pid_alive(os.getpid()) is True
    assert platform_.pid_alive(999999999) is False


def test_pid_alive_never_signals_on_windows(monkeypatch):
    """The safety property, and the whole reason this function exists.

    `os.kill(pid, 0)` probes on POSIX. On Windows CPython special-cases only
    CTRL_C_EVENT and CTRL_BREAK_EVENT and otherwise calls `TerminateProcess`,
    so signal 0 KILLS the target. A stale `watch.lock` holding a recycled pid
    would have terminated an unrelated program; on CI it killed the shell
    running pytest, which is why the Windows leg died with a KeyboardInterrupt
    after all 660 tests had already passed.

    Asserts the negative directly: on Windows, `os.kill` is never reached.
    """
    called: list[object] = []
    monkeypatch.setattr(platform_, "is_windows", lambda: True)
    monkeypatch.setattr(platform_.os, "kill", lambda *a: called.append(a))
    monkeypatch.setattr(platform_, "_pid_alive_windows", lambda _pid: True)

    assert platform_.pid_alive(1234) is True
    assert called == [], "os.kill must never be called on Windows — it terminates"
