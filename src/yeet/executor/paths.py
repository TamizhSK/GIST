"""THE cross-platform helper. C:\\x -> /c/x. Unit-test this on all 3 OSes.

Pure string work with no filesystem access, so the tests can pretend to be any
OS by passing a `PureWindowsPath` — which is the only way to test the Windows
branch from CI's Linux runner as well as its Windows one.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path, PurePath, PureWindowsPath

from yeet.executor.platform_ import is_wsl

CONTAINER_WORKSPACE = "/workspace"
"""Where the job's workspace is bind-mounted inside every job container.
Absolute and fixed: step scripts, `working-directory` and GITHUB_WORKSPACE all
derive from it, and a configurable mount point would buy nothing but bug
reports.

Usually the project root. Under `yeet run --clean` it is the job's own empty
directory, which `actions/checkout` fills — see `workspace.isolated_workspace`."""

CONTAINER_JOB_DIR = "/yeet-run"
"""Where the job's scratch directory is bind-mounted, and ONLY needed when the
workspace is isolated.

`.yeet/tmp/<run>/<job>/` holds the step scripts and the five state files. In a
normal run it sits inside the project root and arrives for free under
/workspace. An isolated workspace is a different directory, so without a second
bind the container would be handed a script path it cannot see."""

WSL_WINDOWS_MOUNT = "/mnt/"
"""WSL mounts the Windows drives here. A repo living under /mnt/c crosses the
9P filesystem boundary on every read — see `warn_if_slow_mount`."""


def to_container_path(host: PurePath) -> str:
    """Host path -> the form the Docker API wants for a bind mount source.

    `C:\\Users\\x\\proj` -> `/c/Users/x/proj`. POSIX paths pass through
    unchanged. The Docker Engine on Windows accepts the drive-letter form too,
    but the `/c/...` form is what works against both a native daemon and one
    reached through WSL integration, which is the combination people actually
    run.
    """
    if isinstance(host, PureWindowsPath) or (_looks_windows(host)):
        win = PureWindowsPath(host)
        drive = win.drive.rstrip(":")
        if not drive:
            # A UNC path (\\server\share) or a drive-relative one. Nothing sane
            # to translate to, so hand back a forward-slashed version and let
            # the daemon reject it with its own message.
            return str(win).replace("\\", "/")
        rest = "/".join(win.parts[1:])
        return f"/{drive.lower()}/{rest}" if rest else f"/{drive.lower()}"
    return str(host)


def _looks_windows(host: PurePath) -> bool:
    """A `Path` created on Linux from a Windows string keeps the backslashes."""
    text = str(host)
    return len(text) >= 2 and text[1] == ":" and text[0].isalpha()


def to_mounted_path(host: Path, base: Path, mount_point: str) -> str:
    """A path under `base` on the host -> where it lands under `mount_point`.

    The general form. A job normally has one bind (the project root at
    /workspace) and an isolated job — `yeet run --clean` — has two, because its
    step scripts live outside the workspace it is given. Both are the same
    question asked about different mounts.
    """
    rel = host.resolve().relative_to(base.resolve())
    tail = rel.as_posix()
    return f"{mount_point}/{tail}" if tail != "." else mount_point


def to_workspace_path(host: Path, root: Path) -> str:
    """A path inside the project -> its location under /workspace.

    Used for step script paths: the script is written to
    `<root>/.yeet/tmp/...` on the host and executed as
    `/workspace/.yeet/tmp/...` inside the container.
    """
    return to_mounted_path(host, root, CONTAINER_WORKSPACE)


def warn_if_slow_mount(root: Path) -> str | None:
    """The /mnt/c warning. Returns None when there is nothing to say.

    Bind-mounting a directory that lives on the Windows filesystem from inside
    WSL routes every read through 9P. It is 10-20x slower, and inotify does not
    fire across the boundary, so `yeet watch` silently stops working. Both
    symptoms look like bugs in this tool, which is why the warning is loud.
    """
    if not is_wsl():
        return None
    if not str(root.resolve()).startswith(WSL_WINDOWS_MOUNT):
        return None
    return (
        f"{root} is on the Windows filesystem ({WSL_WINDOWS_MOUNT}...). "
        "Container I/O will be 10-20x slower and file watching will not fire. "
        "Move the repo under your WSL home (~/) for a dramatic speedup."
    )
