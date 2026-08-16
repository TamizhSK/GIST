"""Walk UPWARD for .git / .yeet / .github/workflows / any ecosystem manifest.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.analyzer.markers import EXTENSION_MARKERS, MARKERS
from yeet.core.config import home_dir

_PRIORITY_GIT = 4
_PRIORITY_YEET = 3
_PRIORITY_GH = 2
_PRIORITY_MARKER = 1

_MARKER_FILES = frozenset(MARKERS)
_MARKER_EXTS = tuple(EXTENSION_MARKERS)


def find_root(start: Path) -> Path:
    """Stop at filesystem root or $HOME. Never shell out to git.

    Priority: .git/ -> .yeet/ -> .github/workflows/ -> any marker file. The
    requirement explicitly includes projects the user just created locally, so
    a directory with two files in it and no VCS must still resolve.
    """
    start = start.expanduser().resolve()
    home = home_dir()  # None in a stripped env; then only the fs root stops us
    cur = start if start.is_dir() else start.parent
    best: tuple[int, Path] | None = None
    while True:
        pri = _priority(cur)
        if pri and (best is None or pri > best[0]):
            best = (pri, cur)
        if best is not None and best[0] == _PRIORITY_GIT:
            break
        if cur == cur.parent or cur == home:
            break
        cur = cur.parent
    if best is not None:
        return best[1]
    return start if start.is_dir() else start.parent


def _priority(d: Path) -> int:
    """Rank the strongest root marker in `d`. 0 means none. `.git` can be a
    FILE too — worktrees are `gitdir:` pointers, and stopping there is correct."""
    if (d / ".git").exists():
        return _PRIORITY_GIT
    if (d / ".yeet").is_dir():
        return _PRIORITY_YEET
    if (d / ".github" / "workflows").is_dir():
        return _PRIORITY_GH
    if _has_marker(d):
        return _PRIORITY_MARKER
    return 0


def _has_marker(d: Path) -> bool:
    if any((d / name).is_file() for name in _MARKER_FILES):
        return True
    for ext in _MARKER_EXTS:
        try:
            if next(d.glob(f"*{ext}"), None) is not None:
                return True
        except OSError:
            continue
    return False
