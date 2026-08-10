"""The expression builtins: contains, startsWith, endsWith, format, join,
toJSON, fromJSON, hashFiles, and success/failure/always/cancelled.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def hash_files(patterns: list[str], root: Path) -> str:
    """SORT the glob results before hashing or you get different hashes per OS.

    That bug is silent: the cache simply never hits on one platform, and you
    lose an afternoon to it. The 3-OS CI matrix asserts a fixed hash for a
    fixed tree precisely to catch it.
    """
    raise NotImplementedError
