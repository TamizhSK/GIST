"""OS + WSL detection, docker socket discovery, /mnt/c slowness warning.

Every `if sys.platform ==` in the codebase belongs in this file or in
`paths.py`. That is deliberate: cross-platform bugs are only findable when the
platform decisions are in one place, and it means the other three developers
never have to think about Windows.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

WSL_MARKER = "microsoft"
"""Both WSL1 and WSL2 put this in /proc/version. WSL2 writes `microsoft-standard`,
WSL1 writes `Microsoft`, hence the lowercased substring test."""

PROC_VERSION = Path("/proc/version")


def is_windows() -> bool:
    """Native Windows. WSL reports `linux` and is deliberately NOT included."""
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    """True on WSL too — WSL *is* Linux as far as the container runtime cares."""
    return sys.platform.startswith("linux")


def is_wsl() -> bool:
    """/proc/version contains 'microsoft'.

    Reading the file is the only reliable test: `WSL_DISTRO_NAME` is unset under
    some init systems and `uname -r` changed format between WSL1 and WSL2.
    Any read failure means "not WSL" — this must never raise, it is called from
    the container setup path.
    """
    if not is_linux():
        return False
    try:
        return WSL_MARKER in PROC_VERSION.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def docker_user() -> str | None:
    """`"uid:gid"` on Linux and WSL, None on macOS and Windows.

    On Linux the container shares the host kernel, so a root container writing
    into the bind-mounted workspace leaves root-owned files behind and the
    user's next `git status` breaks. Passing our own uid/gid fixes it.

    On Docker Desktop the VM already virtualizes ownership, and passing a uid
    that does not exist inside the image breaks things instead of fixing them
    (risk #6). Returning None here means `containers.create(user=None)`, which
    is the same as omitting the argument.
    """
    if is_windows() or is_macos():
        return None
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:  # pragma: no cover - non-POSIX without win32
        return None
    return f"{getuid()}:{getgid()}"


def runner_os() -> str:
    """The value of `RUNNER_OS` / the `runner.os` context. GitHub's vocabulary."""
    if is_windows():
        return "Windows"
    if is_macos():
        return "macOS"
    return "Linux"


def runner_arch() -> str:
    """The value of `RUNNER_ARCH`. GitHub uses X86, X64, ARM, ARM64."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "X64"
    if machine in ("aarch64", "arm64"):
        return "ARM64"
    if machine in ("i386", "i686", "x86"):
        return "X86"
    if machine.startswith("arm"):
        return "ARM"
    return machine.upper()


def docker_host_hint() -> str:
    """What to tell the user when the daemon is unreachable.

    A generic "cannot connect to Docker" is useless — the fix is completely
    different on each platform, and this is the first error a new user hits.
    """
    if is_wsl():
        return (
            "Enable WSL integration: Docker Desktop -> Settings -> Resources -> "
            "WSL Integration, then tick this distro."
        )
    if is_windows() or is_macos():
        return "Is Docker Desktop running? Start it and try again."
    return "Start the daemon: `sudo systemctl start docker` (or `sudo service docker start`)."
