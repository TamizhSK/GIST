"""C6 — the CRLF defence, and shell selection."""

from __future__ import annotations

import pytest

from yeet.executor import script


def test_crlf_never_reaches_disk(tmp_path):
    """Risk #5 / trap #1: `$'\\r': command not found` is invisible in a diff."""
    dest = tmp_path / "step.sh"
    script.write_step_script("echo one\r\necho two\r\n", dest)
    assert b"\r" not in dest.read_bytes()
    assert dest.read_bytes() == b"echo one\necho two\n"


def test_lone_lf_is_untouched(tmp_path):
    dest = tmp_path / "step.sh"
    script.write_step_script("echo hi\n", dest)
    assert dest.read_bytes() == b"echo hi\n"


def test_utf8_survives(tmp_path):
    dest = tmp_path / "step.sh"
    script.write_step_script('echo "we are so back 🚀"', dest)
    assert "🚀" in dest.read_text(encoding="utf-8")


def test_container_default_is_bash_with_pipefail():
    argv = script.shell_argv(None, "/workspace/s.sh", in_container=True)
    assert argv == ["bash", "-e", "-o", "pipefail", "/workspace/s.sh"]


def test_local_default_follows_the_host(monkeypatch):
    monkeypatch.setattr(script, "is_windows", lambda: True)
    assert script.shell_argv(None, "s.ps1", in_container=False)[0] == "pwsh"

    monkeypatch.setattr(script, "is_windows", lambda: False)
    assert script.shell_argv(None, "s.sh", in_container=False)[0] == "bash"


@pytest.mark.parametrize(
    ("shell", "first", "suffix"),
    [
        ("bash", "bash", ".sh"),
        ("sh", "sh", ".sh"),
        ("pwsh", "pwsh", ".ps1"),
        ("python", "python3", ".py"),
    ],
)
def test_explicit_shell_is_honoured(shell, first, suffix):
    assert script.shell_argv(shell, "s", in_container=True)[0] == first
    assert script.script_suffix(shell) == suffix


def test_the_script_path_is_always_last():
    """pwsh's `-File` must be immediately followed by the path."""
    argv = script.shell_argv("pwsh", "C:/s.ps1", in_container=False)
    assert argv[-2:] == ["-File", "C:/s.ps1"]
