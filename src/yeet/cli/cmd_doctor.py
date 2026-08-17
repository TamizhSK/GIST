"""yeet doctor — is this machine able to run a workflow, and if not, why.

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md

Every check answers a question a user would otherwise open an issue about, and
every failure carries the command that fixes it ON THIS platform — "Docker is
not running" is not an answer on a machine where the fix is a WSL integration
toggle. Exit 0 when everything a run needs is present, 1 otherwise, so it can
be the first line of a bug report and the last line of a CI setup step.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from yeet import __version__
from yeet.cli import color_enabled
from yeet.core.config import cache_dir, config_dir
from yeet.executor.platform_ import is_macos, is_windows, is_wsl, runner_arch
from yeet.reporting.theme import SYMBOL_BULLET, SYMBOL_FAIL, SYMBOL_PASS, SYMBOL_WARN

#: The floor from `requires-python`. Below this, nothing else is worth saying.
MIN_PYTHON = (3, 10)

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"

#: `SYMBOL_NOTE` is "note:" — five characters against `[OK]`'s four, which puts
#: a ragged left edge on the one screen a user reads while something is broken.
#: The bullet is the neutral marker and the column is padded below.
_MARKS = {OK: SYMBOL_PASS, WARN: SYMBOL_WARN, FAIL: SYMBOL_FAIL, INFO: SYMBOL_BULLET}
_MARK_W = max(len(mark) for mark in _MARKS.values())
_COLORS = {
    OK: typer.colors.GREEN,
    WARN: typer.colors.YELLOW,
    FAIL: typer.colors.RED,
    INFO: typer.colors.BRIGHT_BLACK,
}


@dataclass(frozen=True, slots=True)
class Check:
    """One line of the report. `fix` is empty when there is nothing to do."""

    name: str
    status: str
    detail: str
    fix: str = ""

    def __post_init__(self) -> None:
        # One check is one line. `DockerUnavailable` carries its own multi-line
        # suggestion, and letting it through put an unindented sentence in the
        # middle of an aligned column — the `fix` line below says it better.
        object.__setattr__(self, "detail", " ".join(self.detail.split()))


def _python() -> Check:
    current = sys.version_info[:3]
    version = ".".join(str(part) for part in current)
    if current[:2] >= MIN_PYTHON:
        return Check("python", OK, f"{version} ({sys.executable})")
    return Check("python", FAIL, f"{version} is below 3.10", _python_upgrade())


def _python_upgrade() -> str:
    if is_windows():
        return "winget install Python.Python.3.12"
    if is_macos():
        return "brew install python@3.12"
    return "sudo apt install python3.12  (or: uv python install 3.12)"


def _docker() -> list[Check]:
    """Reachable daemon, or the fix for THIS platform.

    Imported here rather than at module scope: `yeet doctor` on a machine with
    no Docker at all must still run and say so, and the SDK import is the
    expensive part of this command.
    """
    from yeet.executor.backend import DockerUnavailable, get_docker_client

    try:
        client = get_docker_client()
    except DockerUnavailable as exc:
        return [Check("docker", FAIL, str(exc), _docker_fix())]
    checks = [Check("docker", OK, _docker_version(client))]
    if host := os.environ.get("DOCKER_HOST"):
        checks.append(Check("docker host", INFO, host))
    return checks


def _docker_version(client: object) -> str:
    try:
        info = client.version()  # type: ignore[attr-defined]
        return f"daemon {info.get('Version', '?')} ({info.get('Os', '?')}/{info.get('Arch', '?')})"
    except Exception:  # noqa: BLE001 - the ping already succeeded; this is cosmetic
        return "daemon reachable"


def _docker_fix() -> str:
    if is_wsl():
        return "Docker Desktop -> Settings -> Resources -> WSL integration, enable this distro"
    if is_windows() or is_macos():
        return "start Docker Desktop, then re-run `yeet doctor`"
    return "sudo systemctl start docker  (and: sudo usermod -aG docker $USER, then re-login)"


def _on_path() -> Check:
    """Is the `yeet` the user typed the one they just installed?

    The single most common "it installed but the command isn't found" report,
    and its quieter sibling: two installs, and PATH picks the older one.
    """
    found = shutil.which("yeet")
    if found is None:
        return Check("yeet on PATH", FAIL, "not on PATH", _path_fix())
    ours = Path(sys.argv[0]).resolve()
    if ours.name.startswith("yeet") and Path(found).resolve() != ours:
        return Check("yeet on PATH", WARN, f"PATH finds {found}, this is {ours}", _path_fix())
    return Check("yeet on PATH", OK, found)


def _path_fix() -> str:
    if is_windows():
        return 'add "%LOCALAPPDATA%\\Programs\\yeet\\bin" to PATH, then open a new terminal'
    return 'export PATH="$HOME/.local/bin:$PATH"   (add it to your shell rc)'


def _writable(label: str, directory: Path) -> Check:
    """Config and cache have to be creatable, not merely named.

    A read-only or root-owned directory here fails much later, in the middle of
    a run, as a permission error about a path the user never chose.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".yeet-write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check(label, FAIL, f"{directory}: {exc.strerror or exc}", f"chmod u+w {directory}")
    return Check(label, OK, str(directory))


def _git() -> Check:
    """Not required, but `actions/checkout` and the hooks both want it."""
    found = shutil.which("git")
    if found is None:
        return Check("git", WARN, "not found — checkout falls back to a container", "install git")
    return Check("git", OK, found)


def _workspace_speed() -> list[Check]:
    """WSL's /mnt/c is a 9p mount, and a run there is several times slower."""
    if not is_wsl():
        return []
    cwd = str(Path.cwd())
    if cwd.startswith("/mnt/"):
        return [
            Check(
                "workspace",
                WARN,
                f"{cwd} is a Windows drive mounted into WSL",
                "clone under ~/ instead — /mnt/c is a 9p mount and runs several times slower",
            )
        ]
    return [Check("workspace", OK, cwd)]


def collect() -> list[Check]:
    """Every check, in the order a failure would matter."""
    checks = [
        Check("yeet", INFO, f"{__version__}"),
        _python(),
        Check("platform", INFO, f"{platform.system()} {platform.release()} ({runner_arch()})"),
    ]
    if is_wsl():
        checks.append(Check("wsl", INFO, "running inside WSL"))
    checks.append(_on_path())
    checks.extend(_docker())
    checks.append(_git())
    checks.append(_writable("config dir", config_dir()))
    checks.append(_writable("cache dir", cache_dir()))
    checks.extend(_workspace_speed())
    return checks


def doctor(ctx: typer.Context) -> None:
    """Check this machine can run a workflow, and say how to fix what cannot.

    Example:

        yeet doctor
    """
    color = color_enabled(ctx)
    checks = collect()
    width = max(len(check.name) for check in checks)

    for check in checks:
        mark = _MARKS[check.status].ljust(_MARK_W)
        line = f"{mark} {check.name.ljust(width)}  {check.detail}"
        typer.echo(typer.style(line, fg=_COLORS[check.status]) if color else line)
        if check.fix:
            typer.echo(f"{' ' * (_MARK_W + width + 1)}  -> {check.fix}")

    failed = [check for check in checks if check.status == FAIL]
    typer.echo("")
    if failed:
        what = "problem" if len(failed) == 1 else "problems"
        typer.echo(f"{len(failed)} {what} above will stop a run. Fix, then re-run `yeet doctor`.")
        raise typer.Exit(1)
    typer.echo("Ready. Try `yeet scan` in a project.")
