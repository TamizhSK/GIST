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


def test_the_suffix_matches_the_shell_that_will_run_it(monkeypatch):
    """The Windows regression, and the invariant that was never asserted.

    `shell_argv` applied the platform default and `script_suffix` did not, so a
    step with no `shell:` on Windows was written to `step_1.sh` and handed to
    `pwsh -File` — which takes `.ps1` only. Every job flopped, and the project's
    first-ever CI run went red on windows-latest and nowhere else.

    The test above passed throughout, because it only ever checked argv. The
    two answers have to be checked TOGETHER or the pair can drift again.
    """
    monkeypatch.setattr(script, "is_windows", lambda: True)
    assert script.shell_argv(None, "s", in_container=False)[0] == "pwsh"
    assert script.script_suffix(None, in_container=False) == ".ps1"

    monkeypatch.setattr(script, "is_windows", lambda: False)
    assert script.shell_argv(None, "s", in_container=False)[0] == "bash"
    assert script.script_suffix(None, in_container=False) == ".sh"


def test_a_container_step_is_bash_even_on_a_windows_host(monkeypatch):
    """The image is Linux whatever the host is, so the pair must be bash/.sh."""
    monkeypatch.setattr(script, "is_windows", lambda: True)
    assert script.shell_argv(None, "/workspace/s", in_container=True)[0] == "bash"
    assert script.script_suffix(None, in_container=True) == ".sh"


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
    assert script.script_suffix(shell, in_container=True) == suffix


def test_the_script_path_is_always_last():
    """pwsh's `-File` must be immediately followed by the path."""
    argv = script.shell_argv("pwsh", "C:/s.ps1", in_container=False)
    assert argv[-2:] == ["-File", "C:/s.ps1"]
