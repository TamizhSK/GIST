"""Get a repository onto disk: host `git` if there is one, Docker if there isn't.

Owner: Dev D
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md

WHY THIS FILE EXISTS. Two callers need "put repo X at ref Y in directory Z" and
both had their own half-answer:

* `resolver.resolve_remote` shelled out to `git clone --depth 1 --branch <ref>`.
  That form cannot check out a commit SHA — `--branch` takes a branch or a tag —
  so pinning an action the way W402 tells you to (`uses: foo/bar@<40 hex>`) made
  the clone fail every time. It also inherited the terminal, so a private repo
  stopped the run dead on git's `Username for 'https://github.com':` prompt.
* `actions/checkout` with a `ref:` did nothing at all.

Both now go through `fetch()`. It is init + fetch + checkout rather than
`git clone` because that is the only sequence that treats a branch, a tag and a
SHA identically, and it is the sequence `actions/checkout` itself uses.

It sits in `actions/` (tier 2) next to `resolver.py`, which already ran git, and
NOT in `executor/` or `storage/` — those two are siblings that may not import
each other (docs/adr/0007) and both need this.

DOCKER IS THE FALLBACK, NOT THE DEFAULT. Host git carries the user's SSH agent,
their credential helper, their proxy settings and their `insteadOf` rewrites.
Git inside a container has none of that, so a private repo that works on the
command line would fail there for reasons the log could not explain. Docker is
what we reach for only when there is no `git` on PATH at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_IMAGE = "alpine/git:latest"
"""Tiny (~25MB) and its whole job is git. Only pulled when the host has no git,
and only then — a machine with git never touches Docker for this."""

DEFAULT_TIMEOUT_S = 300.0

SOURCE_MOUNT = "/yeet-source"
"""Where `source_mount` lands inside the git container. Read-only, and only
present when a fetch is fed from a directory outside its own destination."""

VIA_GIT = "git"
VIA_DOCKER = "docker"

NO_GIT_MESSAGE = (
    "cannot fetch a repository: no `git` on PATH and no usable `docker`. "
    "Install git (https://git-scm.com/downloads) or start Docker Desktop."
)

#: The one script, run either by the host shell or by `sh` inside alpine/git.
#: Everything variable arrives through the environment on purpose: a `ref:` of
#: `x; rm -rf ~` interpolated into this text would be a command injection with
#: a workflow file as its delivery mechanism.
_SCRIPT = r"""
set -e
mkdir -p "$YEET_DEST"
git init -q "$YEET_DEST"
cd "$YEET_DEST"
git remote add origin "$YEET_SRC"
if [ "$YEET_DEPTH" = "0" ]; then
  depth=""
else
  depth="--depth=$YEET_DEPTH"
fi
if [ -n "$YEET_REF" ]; then
  # A shallow fetch of one ref is the fast path and it works for a branch, a
  # tag or a SHA. It fails against servers that refuse SHA fetches, so the
  # slow path (all refs, then check out) has to exist or pinned actions break.
  if git fetch $depth --no-tags origin "$YEET_REF" >/dev/null 2>&1; then
    git checkout -q FETCH_HEAD
  else
    echo "shallow fetch of '$YEET_REF' was refused; retrying with full history" >&2
    git fetch --tags origin
    git checkout -q "$YEET_REF"
  fi
else
  git fetch $depth --no-tags origin HEAD
  git checkout -q FETCH_HEAD
fi
if [ -n "$YEET_SUBMODULES" ]; then
  # Failure here is reported, not fatal: a submodule usually points at a second
  # repository the user may have no credentials for, and losing the whole
  # checkout over an optional one would be the wrong trade.
  if [ "$YEET_SUBMODULES" = "recursive" ]; then
    git submodule update --init --recursive $depth || \
      echo "submodules could not be initialised" >&2
  else
    git submodule update --init $depth || echo "submodules could not be initialised" >&2
  fi
fi
# The token, if there was one, is in the remote URL and `git init` just wrote
# it into .git/config inside the user's working tree. Put the clean URL back
# before anyone can commit it by accident.
if [ -n "$YEET_SRC_CLEAN" ]; then
  git remote set-url origin "$YEET_SRC_CLEAN"
fi
git --no-pager log -1 --format=%H
"""

_ENV = {
    # Without this, a private repo makes git block on `Username for ...` with
    # the terminal it inherited — the run hangs and the log says nothing.
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
    # `safe.directory` for THIS invocation only. A bind-mounted repo is owned
    # by a different uid inside the container and git refuses to touch it;
    # `git config --global` would fix that by editing the user's ~/.gitconfig,
    # which is not ours to edit.
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
}


@dataclass(frozen=True, slots=True)
class FetchResult:
    ok: bool
    message: str = ""
    via: str = ""
    commit: str = ""


def have_git() -> bool:
    """Host git AND a POSIX shell to drive it with.

    Both, because `_SCRIPT` is one sh script. A Windows box with Git for
    Windows installed but no `sh` on PATH is a real configuration, and there
    the honest answer is "the host cannot do this" — it falls through to
    Docker rather than running half a script.
    """
    return shutil.which("git") is not None and _host_sh() is not None


def _host_sh() -> str | None:
    return shutil.which("sh") or shutil.which("bash")


def have_docker() -> bool:
    """A `docker` binary that can actually reach a daemon.

    `which docker` alone is not enough: Docker Desktop leaves the CLI on PATH
    when it is not running, and every command then fails with a socket error
    thirty seconds in.
    """
    if shutil.which("docker") is None:
        return False
    try:
        done = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def fetch(
    *,
    mount: Path,
    dest_rel: str,
    source: str,
    ref: str = "",
    depth: int = 1,
    submodules: str = "",
    clean_source: str = "",
    source_mount: Path | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    image: str = GIT_IMAGE,
) -> FetchResult:
    """Put `source` at `ref` into `mount / dest_rel`. Never raises.

    `mount` is the directory bind-mounted into the git container, and
    `dest_rel` is relative to it — so a Docker fallback needs exactly one
    volume, and `source` may itself be `mount` (checking the current repo out
    into a subdirectory of itself, which is what `path:` is for).

    `source_mount` is the second volume, and it is needed exactly once: an
    isolated workspace (`yeet run --clean`) is fed from the project root, which
    is somewhere else entirely on the host. Mounted read-only — this is the
    user's working tree, and nothing here has any business writing to it. Host
    git needs none of this and ignores it.

    `clean_source` is the URL to leave in `.git/config` when `source` carries a
    token. Empty means they are the same and nothing is rewritten.
    """
    dest = (mount / dest_rel) if dest_rel else mount
    env = {
        **_ENV,
        "YEET_SRC": source,
        "YEET_SRC_CLEAN": clean_source,
        "YEET_REF": ref,
        "YEET_DEPTH": str(max(depth, 0)),
        "YEET_SUBMODULES": submodules,
    }

    shell = _host_sh()
    if shell is not None and shutil.which("git") is not None:
        env["YEET_DEST"] = str(dest)
        return _run([shell, "-c", _SCRIPT], env=env, timeout_s=timeout_s, via=VIA_GIT)

    if not have_docker():
        return FetchResult(ok=False, message=NO_GIT_MESSAGE)

    env["YEET_DEST"] = _posix_join("/yeet", dest_rel)
    # The source has to be re-expressed in the CONTAINER's filesystem. When it
    # is the workspace itself — a bare `ref:`, "this repo at that commit" —
    # `source` is a host path that does not exist inside the container, and
    # git fails with "could not read from remote repository", which reads like
    # a network or permissions problem and is neither. It is `/yeet` in there.
    mount_str = str(mount)
    if env["YEET_SRC"] == mount_str:
        env["YEET_SRC"] = "/yeet"
    elif env["YEET_SRC"].startswith(mount_str + "/"):
        env["YEET_SRC"] = _posix_join("/yeet", env["YEET_SRC"][len(mount_str) + 1 :])
    elif source_mount is not None:
        # Same re-expression against the second volume. Checked after `mount`
        # so a source that lives under both still resolves to the writable one.
        src_str = str(source_mount)
        if env["YEET_SRC"] == src_str:
            env["YEET_SRC"] = SOURCE_MOUNT
        elif env["YEET_SRC"].startswith(src_str + "/"):
            env["YEET_SRC"] = _posix_join(SOURCE_MOUNT, env["YEET_SRC"][len(src_str) + 1 :])
    # `-i` (not `-t`): git must never get a TTY to prompt on, and a TTY would
    # also merge stderr into stdout so the commit SHA on the last line stops
    # being the last line.
    argv = ["docker", "run", "--rm", "-i", "-v", f"{mount}:/yeet", "-w", "/yeet"]
    if source_mount is not None:
        argv += ["-v", f"{source_mount}:{SOURCE_MOUNT}:ro"]
    for key, value in env.items():
        argv += ["-e", f"{key}={value}"]
    argv += ["-e", "HOME=/tmp"]
    argv += _user_flags()
    argv += ["--entrypoint", "/bin/sh", image, "-c", _SCRIPT]
    return _run(argv, env=None, timeout_s=timeout_s, via=VIA_DOCKER)


def rev_parse(repo: Path, rev: str) -> str:
    """The commit `rev` names inside `repo`, or "" if git can't say.

    Deliberately host-git-only and deliberately silent on failure: this answers
    "is the ref they asked for the commit we are already sitting on?", and "I
    don't know" and "no" lead to the same place.
    """
    if shutil.which("git") is None:
        return ""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
            capture_output=True,
            timeout=20,
            check=False,
            env={**os.environ, **_ENV},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else ""


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _run(argv: list[str], *, env: dict[str, str] | None, timeout_s: float, via: str) -> FetchResult:
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            env={**os.environ, **env} if env is not None else None,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return FetchResult(ok=False, message=f"the fetch timed out after {timeout_s:.0f}s", via=via)
    except OSError as exc:
        return FetchResult(ok=False, message=f"could not run `{argv[0]}`: {exc}", via=via)

    out = done.stdout.decode("utf-8", "replace").strip()
    if done.returncode != 0:
        return FetchResult(ok=False, message=_why(done.stderr, out), via=via)
    return FetchResult(ok=True, via=via, commit=out.splitlines()[-1].strip() if out else "")


def _why(stderr: bytes, stdout: str) -> str:
    """git's own last words, not ours.

    "fatal: could not read Username" and "Could not resolve host: github.com"
    are the two failures a user actually hits, and both are already sentences.
    Replacing them with "fetch failed" throws away the only useful part.
    """
    text = stderr.decode("utf-8", "replace").strip() or stdout
    lines = [line for line in text.splitlines() if line.strip()]
    return " / ".join(lines[-3:]) if lines else "the fetch failed and said nothing"


def _user_flags() -> list[str]:
    """Write files as the invoking user, not as root.

    Docker on Linux bind-mounts through to the real filesystem, so a checkout
    made by root leaves a directory the user cannot delete without sudo — in
    their own working tree.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:  # Windows
        return []
    return ["-u", f"{getuid()}:{getgid()}"]


def _posix_join(base: str, rel: str) -> str:
    """Container paths are POSIX even when the host is Windows."""
    tail = rel.replace("\\", "/").strip("/")
    return f"{base}/{tail}" if tail else base
