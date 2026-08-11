"""github, env, job, steps, runner, matrix, needs, secrets, inputs, vars.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HEAD = re.compile(r"^ref:\s*(.+)$")
_OWNER_REPO = re.compile(r"^[^:]+:(.+)$")  # scp-style: git@github.com:owner/repo.git
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class Contexts:
    """Everything `${{ }}` can see. Passed by value into each evaluation.

    Unknown context name -> E310, so this list is also the validator's
    allow-list. Keep them in sync.
    """

    github: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    job: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, Any] = field(default_factory=dict)
    runner: dict[str, Any] = field(default_factory=dict)
    matrix: dict[str, Any] = field(default_factory=dict)
    needs: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    root: Path = field(default_factory=Path.cwd)

    NAMES = (
        "github",
        "env",
        "job",
        "steps",
        "runner",
        "matrix",
        "needs",
        "secrets",
        "inputs",
        "vars",
    )


def build_github_context(root: Path, event: str) -> dict[str, object]:
    """The `github` context: the nine fields `executor.env.github_env` promises.

    sha, ref, ref_name, repository, actor, event_name, workspace, run_id,
    run_number. The git-derived fields are read from `.git` with the stdlib —
    no `git` binary, no subprocess — so a freshly created non-git directory
    degrades gracefully to a context without them rather than raising.

    `run_id`/`run_number` prefer the real runner's variables so that a `yeet`
    invoked inside GitHub Actions inherits the truth; otherwise a fresh local
    run id is generated in the same shape the executor uses. `workspace` and
    `event_name` are the only fields guaranteed to be present.
    """
    ctx: dict[str, object] = {
        "workspace": str(root),
        "event_name": event,
        "run_id": os.environ.get("GITHUB_RUN_ID") or _new_run_id(),
        "run_number": int(os.environ.get("GITHUB_RUN_NUMBER") or "1"),
    }

    gitdir = _find_git_dir(root)
    if gitdir is not None:
        ctx.update(_git_context(gitdir))

    actor = os.environ.get("GITHUB_ACTOR")
    if actor:
        ctx["actor"] = actor
    return ctx


# --- git reading (stdlib only) -------------------------------------------------


def _new_run_id() -> str:
    """Same shape as `executor.workspace.new_run_id` — sortable and unique.

    Deliberately not imported: `expressions` may only import from `core`
    (see pyproject.toml's import-linter layers), and the executor is tier 5.
    """
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def _find_git_dir(start: Path) -> Path | None:
    """Walk up to the project's `.git`, honouring worktrees (`gitdir:` files).

    Stops at the filesystem root or the user's home: a `.git` above home is a
    personal config repo, not this project's repository.
    """
    here = start.resolve()
    home = Path.home()
    while here != here.parent and here != home:
        candidate = here / ".git"
        if candidate.is_dir():
            return candidate
        if candidate.is_file():
            return _worktree_gitdir(candidate)
        here = here.parent
    return None


def _worktree_gitdir(gitfile: Path) -> Path | None:
    """A worktree's `.git` is a file containing `gitdir: <path>`."""
    text = gitfile.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("gitdir:"):
            target = Path(line.split(":", 1)[1].strip())
            if not target.is_absolute():
                target = gitfile.parent / target
            return target.resolve()
    return None


def _git_context(gitdir: Path) -> dict[str, str]:
    ctx: dict[str, str] = {}
    head = _read_head(gitdir)
    if head is None:
        return ctx

    match = _HEAD.match(head)
    if match is not None:
        ref = match.group(1).strip()
        ctx["ref"] = ref
        ctx["ref_name"] = _ref_name(ref)
        ctx["sha"] = _resolve_sha(gitdir, ref)
    elif _FULL_SHA.match(head.strip()):
        ctx["sha"] = head.strip()

    repo = _remote_repo(gitdir)
    if repo:
        ctx["repository"] = repo
    return ctx


def _read_head(gitdir: Path) -> str | None:
    head = gitdir / "HEAD"
    if not head.is_file():
        return None
    return head.read_text(encoding="utf-8", errors="replace").strip()


def _ref_name(ref: str) -> str:
    for prefix in ("refs/heads/", "refs/tags/", "refs/remotes/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _resolve_sha(gitdir: Path, ref: str) -> str:
    loose = gitdir / ref
    if loose.is_file():
        value = loose.read_text(encoding="utf-8", errors="replace").strip()
        if _FULL_SHA.match(value):
            return value
    packed = gitdir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and not line.startswith("#") and line.endswith(" " + ref):
                return line.split()[0]
    return ""


def _remote_repo(gitdir: Path) -> str:
    config = gitdir / "config"
    if not config.is_file():
        return ""
    url = _origin_url(config.read_text(encoding="utf-8", errors="replace"))
    if not url:
        return ""
    return _owner_repo(url)


def _origin_url(config_text: str) -> str:
    """The `url =` under `[remote "origin"]`, if any."""
    section = ""
    for line in config_text.splitlines():
        stripped = line.strip()
        header = re.match(r"\[remote\s+\"([^\"]+)\"\]", stripped)
        if header is not None:
            section = header.group(1)
            continue
        if stripped.startswith("["):
            section = ""
            continue
        if section == "origin":
            url = re.match(r"url\s*=\s*(.+)$", stripped)
            if url is not None:
                return url.group(1).strip()
    return ""


def _owner_repo(url: str) -> str:
    """`git@github.com:me/proj.git` or `https://github.com/me/proj` -> `me/proj`."""
    rest = url
    if "://" in rest:
        rest = rest.split("://", 1)[1]
    if "@" in rest:
        rest = rest.rsplit("@", 1)[1]
    match = _OWNER_REPO.match(rest)
    if match is not None:
        rest = match.group(1)
    parts = [p for p in rest.split("/") if p]
    owner_repo = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")
    return owner_repo.removesuffix(".git")
