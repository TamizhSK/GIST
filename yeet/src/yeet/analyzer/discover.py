"""Walk DOWNWARD for flow files. Exclude list + depth cap + inode set + PermissionError.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

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
    ".yeet/tmp",
    ".yeet/runs",
}

FOREIGN_CI = {".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"}
"""Detected and reported as unsupported, never parsed. Saying "found a GitLab
CI file, not supported" costs five lines and reads as deliberate."""

YEET_FLOW_SUFFIXES = {".yml", ".yaml", ".json"}
GH_FLOW_SUFFIXES = {".yml", ".yaml"}
ROOT_FLOW_NAMES = ("yeet.yml", "yeet.yaml", "yeet.json", ".yeet.yml")

# Precedence for the returned list: .yeet/flows/ first, then .github/workflows/,
# then a root-level single-file project. Lower number = earlier.
_ORDER_YEET = 0
_ORDER_GITHUB = 1
_ORDER_ROOT = 2


@dataclass
class Discovery:
    flows: list[Path] = field(default_factory=list)
    foreign_ci: list[Path] = field(default_factory=list)
    truncated: bool = False


def discover_flows(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (flows, foreign_ci).

    Flows are in precedence order: .yeet/flows/ > .github/workflows/ > a root
    yeet.yml. Track visited inodes to break symlink and junction loops, and
    wrap every scandir in a PermissionError handler — on a corporate laptop you
    WILL hit directories you cannot read, and crashing there is a bad first
    impression.
    """
    found = _discover(root)
    return found.flows, found.foreign_ci


def discover(root: Path) -> Discovery:
    """Like discover_flows, but also reports `truncated` for the scan header."""
    return _discover(root)


def _discover(root: Path) -> Discovery:
    root = root.expanduser().resolve()
    spec = _load_ignore_spec(root)
    visited: set[tuple[int, int]] = set()
    seen = 0
    truncated = False
    found = Discovery()
    ranked: list[tuple[int, Path]] = []

    def walk(d: Path, depth: int) -> None:
        nonlocal seen, truncated
        if truncated or depth > MAX_DEPTH:
            return
        try:
            st = d.stat()
        except OSError:
            return
        inode = (st.st_dev, st.st_ino)
        if inode in visited:
            return
        visited.add(inode)
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except PermissionError:
            return
        except OSError:
            return
        for entry in entries:
            if seen >= MAX_FILES:
                truncated = True
                return
            seen += 1
            name = entry.name
            path = d / name
            rel = path.relative_to(root)
            rel_posix = rel.as_posix()
            try:
                is_dir = entry.is_dir(follow_symlinks=FOLLOW_SYMLINKS)
            except OSError:
                continue
            if _is_ignored(spec, rel_posix, is_dir):
                continue
            if is_dir:
                if name in EXCLUDE_DIRS or rel_posix in EXCLUDE_DIRS:
                    continue
                walk(path, depth + 1)
            else:
                try:
                    if entry.is_file(follow_symlinks=False):
                        _classify(rel, path, found, ranked)
                except OSError:
                    continue

    walk(root, 0)
    found.flows = [p for _, p in sorted(ranked, key=lambda item: (item[0], item[1].name))]
    found.truncated = truncated
    return found


def _classify(rel: Path, path: Path, found: Discovery, ranked: list[tuple[int, Path]]) -> None:
    parts = rel.parts
    if parts[-1] in FOREIGN_CI:
        found.foreign_ci.append(path)
        return
    if len(parts) == 1 and rel.name in ROOT_FLOW_NAMES:
        ranked.append((_ORDER_ROOT, path))
        return
    if (
        len(parts) == 3
        and parts[0] == ".yeet"
        and parts[1] == "flows"
        and rel.suffix in YEET_FLOW_SUFFIXES
    ):
        ranked.append((_ORDER_YEET, path))
        return
    if (
        len(parts) == 3
        and parts[0] == ".github"
        and parts[1] == "workflows"
        and rel.suffix in GH_FLOW_SUFFIXES
    ):
        ranked.append((_ORDER_GITHUB, path))
        return


def _load_ignore_spec(root: Path) -> pathspec.PathSpec[pathspec.Pattern]:
    patterns: list[str] = []
    for name in (".gitignore", ".yeetignore"):
        ignore_file = root / name
        if not ignore_file.is_file():
            continue
        try:
            patterns.extend(ignore_file.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _is_ignored(spec: pathspec.PathSpec[pathspec.Pattern], rel_posix: str, is_dir: bool) -> bool:
    if spec.match_file(rel_posix):
        return True
    return is_dir and spec.match_file(rel_posix + "/")
