"""Walk DOWNWARD for flow files. Exclude list + depth cap + inode set + PermissionError.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

MAX_DEPTH = 5
MAX_FILES = 20_000
FOLLOW_SYMLINKS = False

EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target", "out",
    ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".gradle", ".next", ".nuxt", "bin", "obj",
}


def discover_flows(root: Path) -> list[Path]:
    raise NotImplementedError
