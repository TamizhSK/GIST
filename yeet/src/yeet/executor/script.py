"""Write a step's script to disk. ALWAYS LF — CRLF kills bash in the container.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import shutil
from pathlib import Path

from yeet.executor.platform_ import is_windows

DEFAULT_CONTAINER_SHELL = "bash"
DEFAULT_POSIX_SHELL = "bash"
DEFAULT_WINDOWS_SHELL = "pwsh"
WINDOWS_FALLBACK_SHELL = "powershell"

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


def default_shell(*, in_container: bool) -> str:
    """The shell a step with no `shell:` runs under, resolved once.

    In a container it is always bash — we control the image. On the host it
    follows the platform; on Windows it is pwsh when installed and the
    PowerShell the OS ships otherwise (plan.md C13).
    """
    if in_container:
        return DEFAULT_CONTAINER_SHELL
    if not is_windows():
        return DEFAULT_POSIX_SHELL
    return DEFAULT_WINDOWS_SHELL if shutil.which("pwsh") else WINDOWS_FALLBACK_SHELL


def shell_argv(shell: str | None, script_path: str, *, in_container: bool) -> list[str]:
    """The argv that runs `script_path` under the step's `shell:`.

    In a container the default is always bash — we control the image, and the
    base image has it. On the host it depends on the platform, because Windows
    has neither bash nor a POSIX shell by default.
    """
    name = (shell or "").strip().lower()
    if not name:
        name = default_shell(in_container=in_container)
    argv = list(_ARGV.get(name, ["bash", "-e"]))
    argv.append(script_path)
    return argv


def script_suffix(shell: str | None, *, in_container: bool = False) -> str:
    """`.sh`, `.ps1`, `.py` — pwsh refuses to run a file without `.ps1`.

    The suffix and the argv must resolve the default the same way, or the host
    gets a `.sh` file handed to pwsh — which refuses it.
    """
    name = (shell or "").strip().lower()
    if not name:
        name = default_shell(in_container=in_container)
    return SUFFIXES.get(name, ".sh")
