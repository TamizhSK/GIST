"""Walk DOWNWARD for flow files. Exclude list + depth cap + inode set + PermissionError.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

MAX_DEPTH = 5
MAX_FILES = 20_000
FOLLOW_SYMLINKS = False

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "out",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".gradle",
    ".next",
    ".nuxt",
    "bin",
    "obj",
}

FOREIGN_CI = {".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"}
"""Detected and reported as unsupported, never parsed. Saying "found a GitLab
CI file, not supported" costs five lines and reads as deliberate."""


def discover_flows(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (flows, foreign_ci).

    Flows are in precedence order: .yeet/flows/ > .github/workflows/ > a root
    yeet.yml. Track visited inodes to break symlink and junction loops, and
    wrap every scandir in a PermissionError handler — on a corporate laptop you
    WILL hit directories you cannot read, and crashing there is a bad first
    impression.
    """
    raise NotImplementedError
