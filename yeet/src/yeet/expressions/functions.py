"""contains, startsWith, endsWith, format, join, toJSON, fromJSON, hashFiles, success/failure/always/cancelled.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""
from __future__ import annotations

def hash_files(patterns: list[str], root: Path) -> str:
    """SORT the glob results before hashing or you get different hashes per OS."""
    raise NotImplementedError
