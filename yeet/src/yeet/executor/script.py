"""Write a step's script to disk. ALWAYS LF — CRLF kills bash in the container.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import shutil
from pathlib import Path

from yeet.executor import platform_

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


def resolve_shell(shell: str | None, *, in_container: bool) -> str:
    """The shell a step actually gets, with the platform default applied.

    ONE resolution, used by both `shell_argv` and `script_suffix`. They used to
    resolve separately and only `shell_argv` applied the default, so on Windows
    a step with no `shell:` was written to `step_1.sh` and then handed to
    `pwsh -File` — which refuses anything but `.ps1`, exactly as the note on
    `script_suffix` says. Every job on Windows flopped, and the first CI run
    the project ever performed went red on windows-latest for this reason.

    Two functions deriving the same default independently is the shape of the
    bug; deleting the second derivation is the fix.

    On the host, Windows defaults to pwsh when installed and the PowerShell the
    OS ships otherwise (plan.md C13) — a stock Windows box without PowerShell
    Core must still be able to run `cooked_on: local` jobs.
    """
    name = (shell or "").strip().lower()
    if name:
        return name
    if in_container:
        return DEFAULT_CONTAINER_SHELL
    if not platform_.is_windows():
        return DEFAULT_POSIX_SHELL
    return DEFAULT_WINDOWS_SHELL if shutil.which("pwsh") else WINDOWS_FALLBACK_SHELL


def shell_argv(shell: str | None, script_path: str, *, in_container: bool) -> list[str]:
    """The argv that runs `script_path` under the step's `shell:`.

    In a container the default is always bash — we control the image, and the
    base image has it. On the host it depends on the platform, because Windows
    has neither bash nor a POSIX shell by default.

    argv[0] goes through `shell_executable` so that `shell: bash` on Windows
    reaches Git Bash rather than System32's WSL launcher. Inside a container it
    is a no-op — the image is Linux and `bash` means bash there.
    """
    argv = list(_ARGV.get(resolve_shell(shell, in_container=in_container), ["bash", "-e"]))
    if not in_container:
        argv[0] = platform_.shell_executable(argv[0])
    argv.append(script_path)
    return argv


def script_suffix(shell: str | None, *, in_container: bool) -> str:
    """`.sh`, `.ps1`, `.py` — pwsh refuses to run a file without `.ps1`.

    `in_container` is required rather than defaulted: the answer genuinely
    differs between the two backends on the same machine, and a default here
    would silently reintroduce the Windows bug the moment someone forgot it.
    """
    return SUFFIXES.get(resolve_shell(shell, in_container=in_container), ".sh")
