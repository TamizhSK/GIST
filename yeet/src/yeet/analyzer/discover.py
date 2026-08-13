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

MAX_DEPTH = 6
"""Deep enough for `apps/<svc>/<pkg>/.github/workflows/ci.yml` in a monorepo.

The cap exists so pointing yeet at `$HOME` by mistake terminates; it is not a
statement about how deep a workflow may live. Once the walk is INSIDE a
recognised flow directory the cap is lifted (`_walk`), because
`.github/workflows/reusable/build.yml` is a real layout and truncating it would
silently drop a file the user can see with `ls`.
"""

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
# then a bare workflows/ directory, then a root-level single-file project.
# Lower number = earlier.
_ORDER_YEET = 0
_ORDER_GITHUB = 1
_ORDER_BARE = 2
_ORDER_ROOT = 3

#: Directory chains that mean "the files under here are workflows", matched at
#: ANY depth and with any number of subdirectories beneath them.
#:
#: `("workflows",)` on its own is what makes a plain `workflows/ci.yml` work —
#: GitLab-style layouts, `ci/workflows/`, and every repo that keeps its
#: pipelines somewhere other than `.github/`. It sits BELOW `.github/workflows`
#: in precedence because a repo that has both means the `.github` one.
_FLOW_DIRS: tuple[tuple[tuple[str, ...], int, frozenset[str]], ...] = (
    ((".yeet", "flows"), _ORDER_YEET, frozenset(YEET_FLOW_SUFFIXES)),
    ((".github", "workflows"), _ORDER_GITHUB, frozenset(GH_FLOW_SUFFIXES)),
    ((".gitea", "workflows"), _ORDER_GITHUB, frozenset(GH_FLOW_SUFFIXES)),
    ((".forgejo", "workflows"), _ORDER_GITHUB, frozenset(GH_FLOW_SUFFIXES)),
    ((".yeet",), _ORDER_YEET, frozenset(YEET_FLOW_SUFFIXES)),
    (("workflows",), _ORDER_BARE, frozenset(GH_FLOW_SUFFIXES)),
    (("flows",), _ORDER_BARE, frozenset(GH_FLOW_SUFFIXES)),
)

#: Subdirectories of a `.yeet/` that a RUN writes to. They are not flows and
#: descending into them on a busy project is thousands of wasted stats.
_YEET_RUNTIME_DIRS = frozenset({"tmp", "runs", "artifacts", "cache", "actions"})

#: How each flow was found, for `yeet scan`'s report. Keyed by the order rank.
SOURCE_LABELS = {
    _ORDER_YEET: "yeet",
    _ORDER_GITHUB: "github",
    _ORDER_BARE: "workflows",
    _ORDER_ROOT: "root",
}


@dataclass
class Discovery:
    flows: list[Path] = field(default_factory=list)
    foreign_ci: list[Path] = field(default_factory=list)
    truncated: bool = False
    sources: dict[Path, str] = field(default_factory=dict)
    """flow path -> one of SOURCE_LABELS. `yeet scan` prints it so a user who
    did not expect `docs/workflows/example.yml` to be picked up can see why."""


def discover_flows(root: Path) -> tuple[list[Path], list[Path]]:
    """Return (flows, foreign_ci).

    Flows are in precedence order: `.yeet/flows/` > `.github/workflows/` >
    a bare `workflows/` directory > a root `yeet.yml`. Each of those
    directories is matched at ANY depth, with any nesting beneath it, so a
    monorepo's `packages/api/.github/workflows/ci.yml` is found by the same
    walk that finds the one at the top.

    Track visited inodes to break symlink and junction loops, and wrap every
    scandir in a PermissionError handler — on a corporate laptop you WILL hit
    directories you cannot read, and crashing there is a bad first impression.
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

    def walk(d: Path, depth: int, *, inside_flow_dir: bool) -> None:
        nonlocal seen, truncated
        if truncated:
            return
        if depth > MAX_DEPTH and not inside_flow_dir:
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
                if name in EXCLUDE_DIRS or _is_yeet_runtime_dir(rel.parts):
                    continue
                walk(path, depth + 1, inside_flow_dir=_rank_of_dir(rel.parts) is not None)
            else:
                try:
                    if entry.is_file(follow_symlinks=False):
                        _classify(rel, path, found, ranked)
                except OSError:
                    continue

    walk(root, 0, inside_flow_dir=_rank_of_dir(()) is not None)
    ranked.sort(key=lambda item: (item[0], len(item[1].parts), item[1].name))
    found.flows = [p for _, p in ranked]
    found.sources = {p: SOURCE_LABELS[rank] for rank, p in ranked}
    found.truncated = truncated
    return found


def _is_yeet_runtime_dir(parts: tuple[str, ...]) -> bool:
    """`.yeet/tmp`, `.yeet/runs`, … at any depth — a run's own scratch space.

    This used to be spelled as `.yeet/tmp` entries in EXCLUDE_DIRS compared
    against the root-relative path, which stopped working the moment a
    sub-package had its own `.yeet/`. The pair of names is the whole rule.
    """
    return len(parts) >= 2 and parts[-2] == ".yeet" and parts[-1] in _YEET_RUNTIME_DIRS


def _rank_of_dir(parts: tuple[str, ...]) -> int | None:
    """Is this directory (root-relative) a flow directory, and at what rank?

    Matched on the TAIL of the path, so `.github/workflows` counts wherever it
    appears. `()` — the root itself — is checked against the single-segment
    chains, which is what makes `yeet scan .github/workflows` work: point the
    tool straight at a workflow directory and it reads the files in it.
    """
    best: int | None = None
    for chain, rank, _ in _FLOW_DIRS:
        if _tail_matches(parts, chain) and (best is None or rank < best):
            best = rank
    return best


def _tail_matches(parts: tuple[str, ...], chain: tuple[str, ...]) -> bool:
    return len(parts) >= len(chain) and parts[len(parts) - len(chain) :] == chain


def _classify(rel: Path, path: Path, found: Discovery, ranked: list[tuple[int, Path]]) -> None:
    """One file -> foreign CI, a ranked flow, or nothing.

    The flow test walks the file's ancestor directories from the deepest
    upward, so `.github/workflows/reusable/build.yml` matches on
    `.github/workflows` two levels up and keeps that rank. Deepest-first also
    means `.yeet/flows` inside a `.github/workflows` tree (nobody does this,
    but the walk allows it) is ranked by the directory it actually sits in.
    """
    parts = rel.parts
    if parts[-1] in FOREIGN_CI:
        found.foreign_ci.append(path)
        return
    if len(parts) == 1 and rel.name in ROOT_FLOW_NAMES:
        ranked.append((_ORDER_ROOT, path))
        return
    dirs = parts[:-1]
    for cut in range(len(dirs), -1, -1):
        for chain, rank, suffixes in _FLOW_DIRS:
            if _tail_matches(dirs[:cut], chain) and rel.suffix in suffixes:
                ranked.append((rank, path))
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
