"""analyze(path) -> Project. The public face of this package.

The `Project` dataclass itself lives in `core.project`, not here: `reporting`
formats one for `yeet scan` and tier 1 may not import tier 2.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.analyzer.discover import discover
from yeet.analyzer.fingerprint import fingerprint
from yeet.analyzer.root import find_root
from yeet.core.project import Project

_HEAD_PREFIX = "ref: refs/heads/"


def analyze(start: Path) -> Project:
    """Root detection -> discovery -> fingerprint. See architecture.md 3.9.

    Touches the filesystem only. No YAML is parsed at this stage — that is the
    parser's job, and keeping the split means `yeet scan` stays fast on repos
    with a hundred workflow files.
    """
    root = find_root(start)
    found = discover(root)
    is_git = (root / ".git").exists()
    return Project(
        root=root,
        flows=found.flows,
        foreign_ci=found.foreign_ci,
        ecosystems=fingerprint(root),
        is_git=is_git,
        branch=_branch(root) if is_git else None,
        dockerfile=_dockerfile(root),
        truncated=found.truncated,
        flow_sources=found.sources,
    )


def _branch(root: Path) -> str | None:
    """Read `.git/HEAD` directly — never shell out to git.

    A detached HEAD (`HEAD` holds a SHA, not a `ref:` line) yields None. A
    worktree `.git` is a FILE pointing at the real git dir; `Path.read_text` on
    that file would read the wrong thing, so keep this to the plain-repo case
    and let a None branch read as "not on a branch".
    """
    head = root / ".git" / "HEAD"
    try:
        line = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if line.startswith(_HEAD_PREFIX):
        return line[len(_HEAD_PREFIX) :]
    return None


def _dockerfile(root: Path) -> Path | None:
    candidate = root / "Dockerfile"
    return candidate if candidate.is_file() else None
