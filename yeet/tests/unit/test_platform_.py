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
