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
import shutil
import sys
from pathlib import Path

POSIX_SHELLS = ("bash", "sh")

GIT_BASH_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)
"""Where Git for Windows puts bash. Checked before anything on PATH.

`C:\\Windows\\System32\\bash.exe` — which is what bare `bash` resolves to on a
stock Windows box, and on GitHub's windows-latest runner — is the **WSL
launcher**, not a shell. With no distribution installed it prints "Windows
Subsystem for Linux has no installed distributions" (in UTF-16, to add insult)
and exits non-zero, so every `shell: bash` step fails with a message about
Linux distributions that has nothing to do with the workflow. GitHub Actions
itself never invokes bare `bash` on Windows for exactly this reason.
"""

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


def shell_executable(name: str) -> str:
    """The program to actually exec for a shell name. Only Windows differs.

    Returns `name` unchanged everywhere except Windows + `bash`/`sh`, where
    bare `bash` is System32's WSL launcher rather than a shell — see
    GIT_BASH_CANDIDATES. Git for Windows is looked for in its two install
    locations, then derived from `git` on PATH (`…/cmd/git.exe` ->
    `…/bin/bash.exe`), and only then do we give up and return the bare name so
    the failure is the user's PATH rather than ours.
    """
    if not is_windows() or name not in POSIX_SHELLS:
        return name

    for candidate in GIT_BASH_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    git = shutil.which("git")
    if git is not None:
        bash = Path(git).parent.parent / "bin" / "bash.exe"
        if bash.is_file():
            return str(bash)

    return name


def pid_alive(pid: int) -> bool:
    """Is this pid a running process? **Probes. Never signals.**

    `os.kill(pid, 0)` is the POSIX idiom and it is actively dangerous on
    Windows: CPython's `os.kill` there special-cases only CTRL_C_EVENT and
    CTRL_BREAK_EVENT and otherwise calls `TerminateProcess(handle, sig)` — so
    signal 0, the "just checking" signal everywhere else, KILLS the process.

    A stale `watch.lock` holding a recycled pid would therefore terminate an
    unrelated program on the user's machine. It also killed the CI shell: the
    lock test writes `os.getppid()` to look "alive and not us", and probing it
    on windows-latest terminated the pwsh process running the step, so the
    whole pytest session died with a KeyboardInterrupt after the test had
    already passed.

    On Windows we ask the kernel instead. A process that exited with code 259
    (STILL_ACTIVE) is indistinguishable from a running one; that is a
    documented quirk of the API and is not worth a second syscall here, since
    the only cost is declining to take over one stale lock.
    """
    if is_windows():
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259

    # `getattr` rather than `ctypes.windll.kernel32`: the attribute only exists
    # on Windows, so a direct reference needs `# type: ignore[attr-defined]`
    # off Windows and mypy then rejects that same ignore ON Windows as unused
    # (`warn_unused_ignores`). One spelling cannot satisfy a strict run on both,
    # and CI type-checks on all three. This needs no ignore anywhere.
    kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return bool(code.value == still_active)
        return True  # it exists; we just cannot read its status
    finally:
        kernel32.CloseHandle(handle)


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


def docker_host_candidates() -> list[str]:
    """Every endpoint worth trying when `docker.from_env()` cannot connect.

    THE BUG THIS EXISTS FOR. `docker.from_env()` reads `$DOCKER_HOST` and
    nothing else. The `docker` CLI reads `docker context`, which is a JSON file
    under `~/.docker/contexts/` that no environment variable mentions. Every
    non-Docker-Desktop runtime — Colima, Rancher Desktop, Podman, Lima, rootless
    dockerd — installs itself by creating a context and NOT by exporting
    `DOCKER_HOST`. On those machines `docker ps` works perfectly in the terminal
    while yeet says "no Docker daemon is listening", and the user is looking at
    a running daemon being told it does not exist. It is the single most
    confusing failure this tool can produce, because the evidence in front of
    them contradicts it.

    So: the active context first (that is what the CLI itself would use), then
    the well-known socket of every runtime that ships one. Ordered by how
    likely it is to be the one the user means, and de-duplicated.

    Cheap on purpose — no subprocess. `docker context inspect` would be the
    tidy way to ask and it costs 200-800 ms of CLI startup on a cold cache, on
    a path that runs before every single container job.
    """
    found: list[str] = []

    def add(host: str | None) -> None:
        if host and host not in found:
            found.append(host)

    add(_context_host())

    if is_windows():
        # The two named pipes Docker Desktop publishes. The Linux-engine one is
        # what a WSL2 backend listens on and it is the default on every modern
        # install; `docker_engine` is the Windows-containers/older-Desktop pipe.
        add("npipe:////./pipe/dockerDesktopLinuxEngine")
        add("npipe:////./pipe/docker_engine")
        return found

    for path in _socket_candidates():
        if path.exists():
            add(f"unix://{path}")
    return found


def _socket_candidates() -> list[Path]:
    """Where each runtime puts its socket on macOS, Linux and WSL.

    Existence-checked by the caller rather than probed: connecting to an absent
    socket costs a full connect timeout each, and there are eight of them.
    """
    home = Path.home()
    paths = [
        Path("/var/run/docker.sock"),  # system dockerd, and WSL integration
        home / ".docker" / "run" / "docker.sock",  # Docker Desktop 4.13+
        home / ".colima" / "default" / "docker.sock",  # Colima, default profile
        home / ".colima" / "docker.sock",  # Colima, older layout
        home / ".rd" / "docker.sock",  # Rancher Desktop
        home / ".lima" / "docker" / "sock" / "docker.sock",  # Lima
        # Podman's Docker-compatible socket. It speaks the same API, and a
        # `podman machine` user has no dockerd at all — refusing to look here
        # would mean telling them to install Docker when they deliberately did
        # not.
        home / ".local" / "share" / "containers" / "podman" / "machine" / "podman.sock",
    ]
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        paths.append(Path(runtime_dir) / "docker.sock")  # rootless dockerd
        paths.append(Path(runtime_dir) / "podman" / "podman.sock")
    return paths


def _context_host() -> str | None:
    """The endpoint the `docker` CLI itself would use, read from its own files.

    `$DOCKER_CONTEXT` overrides `~/.docker/config.json`'s `currentContext`,
    which is the same precedence the CLI applies. The `default` context has no
    stored metadata — it means "the built-in default", which is exactly what
    `from_env()` already tried — so it is skipped rather than searched for.

    Any malformed file at all means "no answer": this is a best-effort lookup
    on the error path, and an exception here would replace "Docker is not
    running" with a traceback about JSON.
    """
    config_dir = Path(os.environ.get("DOCKER_CONFIG") or (Path.home() / ".docker"))
    name = os.environ.get("DOCKER_CONTEXT") or _current_context(config_dir)
    if not name or name == "default":
        return None

    meta_root = config_dir / "contexts" / "meta"
    try:
        metas = sorted(meta_root.glob("*/meta.json"))
    except OSError:
        return None
    for meta in metas:
        host = _host_from_meta(meta, name)
        if host:
            return host
    return None


def _current_context(config_dir: Path) -> str | None:
    import json

    try:
        data = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("currentContext") if isinstance(data, dict) else None
    return str(name) if name else None


def _host_from_meta(meta: Path, wanted: str) -> str | None:
    """`{"Name": …, "Endpoints": {"docker": {"Host": …}}}` — or nothing.

    Every context directory is scanned and matched on the recorded `Name`
    rather than computed from it. The directory IS the SHA-256 of the name, but
    reimplementing that here means a silent miss the day Docker changes it, and
    there are only ever a handful of contexts to read.
    """
    import json

    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("Name") != wanted:
        return None
    endpoints = data.get("Endpoints")
    docker = endpoints.get("docker") if isinstance(endpoints, dict) else None
    host = docker.get("Host") if isinstance(docker, dict) else None
    return str(host) if host else None


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
