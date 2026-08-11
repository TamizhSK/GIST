"""Write a step's script to disk. ALWAYS LF — CRLF kills bash in the container.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.executor.platform_ import is_windows

DEFAULT_CONTAINER_SHELL = "bash"
DEFAULT_POSIX_SHELL = "bash"
DEFAULT_WINDOWS_SHELL = "pwsh"

_ARGV: dict[str, list[str]] = {
    # `-e` so a failing command fails the step. GitHub adds `-o pipefail` for
    # bash too; W405 is the lint that nudges users to be explicit about it.
    "bash": ["bash", "-e", "-o", "pipefail"],
    "sh": ["sh", "-e"],
    "pwsh": ["pwsh", "-NoProfile", "-NonInteractive", "-File"],
    "powershell": ["powershell", "-NoProfile", "-NonInteractive", "-File"],
    "python": ["python3", "-u"],
    "node": ["node"],
}

SUFFIXES: dict[str, str] = {
    "bash": ".sh",
    "sh": ".sh",
    "pwsh": ".ps1",
    "powershell": ".ps1",
    "python": ".py",
    "node": ".js",
}


def write_step_script(text: str, dest: Path) -> None:
    """Write LF bytes. Unconditionally, on every platform.

    Trap #1 on the guide's list: a script written with CRLF makes bash inside
    the container die with `$'\\r': command not found`, and the error names a
    character the user cannot see. `.gitattributes` and `core.autocrlf input`
    are the other two layers of the same defence — this one is the only one
    that cannot be bypassed by a misconfigured machine.
    """
    dest.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def shell_argv(shell: str | None, script_path: str, *, in_container: bool) -> list[str]:
    """The argv that runs `script_path` under the step's `shell:`.

    In a container the default is always bash — we control the image, and the
    base image has it. On the host it depends on the platform, because Windows
    has neither bash nor a POSIX shell by default.
    """
    name = (shell or "").strip().lower()
    if not name:
        if in_container:
            name = DEFAULT_CONTAINER_SHELL
        else:
            name = DEFAULT_WINDOWS_SHELL if is_windows() else DEFAULT_POSIX_SHELL
    argv = list(_ARGV.get(name, ["bash", "-e"]))
    argv.append(script_path)
    return argv


def script_suffix(shell: str | None) -> str:
    """`.sh`, `.ps1`, `.py` — pwsh refuses to run a file without `.ps1`."""
    name = (shell or "").strip().lower()
    return SUFFIXES.get(name, ".sh")
