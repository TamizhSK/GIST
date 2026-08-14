"""C3 — path translation. PureWindowsPath means the Windows rows run on Linux too."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from yeet.executor import paths


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (PureWindowsPath(r"C:\Users\x\proj"), "/c/Users/x/proj"),
        (PureWindowsPath(r"D:\repos\yeet"), "/d/repos/yeet"),
        (PureWindowsPath("C:\\"), "/c"),
        (PurePosixPath("/home/x/proj"), "/home/x/proj"),
        (PurePosixPath("/Users/x/proj"), "/Users/x/proj"),
    ],
)
def test_to_container_path(host, expected):
    assert paths.to_container_path(host) == expected


def test_windows_string_on_a_posix_host():
    """A Path built from a Windows string keeps its backslashes — detect it."""
    assert paths.to_container_path(Path(r"C:\Users\x")) == "/c/Users/x"


def test_to_workspace_path_is_relative_to_the_mount(tmp_path):
    script = tmp_path / ".yeet" / "tmp" / "run" / "step-1" / "script.sh"
    script.parent.mkdir(parents=True)
    script.touch()
    assert paths.to_workspace_path(script, tmp_path) == "/workspace/.yeet/tmp/run/step-1/script.sh"


def test_no_slow_mount_warning_off_wsl(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_wsl", lambda: False)
    assert paths.warn_if_slow_mount(tmp_path) is None


def test_slow_mount_warning_fires_under_mnt_c(monkeypatch):
    monkeypatch.setattr(paths, "is_wsl", lambda: True)

    class FakeRoot:
        def resolve(self):
            return "/mnt/c/Users/x/proj"

        def __str__(self):
            return "/mnt/c/Users/x/proj"

    warning = paths.warn_if_slow_mount(FakeRoot())  # type: ignore[arg-type]
    assert warning is not None
    assert "10-20x slower" in warning


def test_no_warning_for_a_wsl_home_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "is_wsl", lambda: True)
    assert paths.warn_if_slow_mount(tmp_path) is None
