"""upload/download artifacts -> .yeet/artifacts/<run-id>/<name>/.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md

`store_artifact` takes GLOB PATTERNS, not a single path, because that is what
`actions/upload-artifact` takes and what every real workflow writes:

    with: {name: dist, path: "dist/**"}
    with: {name: logs, path: "**/*.log"}

Relative layout inside the artifact is preserved against the workspace root, so
`download-artifact` puts files back where the producing job had them.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def store_artifact(root: Path, run_id: str, name: str, patterns: list[str], *, base: Path) -> int:
    """Copy everything matching `patterns` into the artifact directory.

    Returns the number of FILES stored — zero is a legitimate answer and the
    caller reports it, because `path:` that matches nothing is the most common
    upload-artifact mistake and GitHub warns about it rather than failing.
    """
    dest_root = artifact_dir(root, run_id, name)
    stored = 0
    for pattern in patterns:
        for src in _expand(base, pattern):
            if not src.is_file():
                continue
            rel = _relative(src, base)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            stored += 1
    return stored


def load_artifact(root: Path, run_id: str, name: str, dest: Path) -> int:
    """Copy a stored artifact back into `dest`. Returns the file count."""
    source = artifact_dir(root, run_id, name)
    if not source.is_dir():
        return 0
    restored = 0
    for src in sorted(source.rglob("*")):
        if not src.is_file():
            continue
        target = dest / src.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        restored += 1
    return restored


def artifact_dir(root: Path, run_id: str, name: str) -> Path:
    return root / ".yeet" / "artifacts" / run_id / name


def list_artifacts(root: Path, run_id: str) -> list[Path]:
    """The artifact directories of one run."""
    base = root / ".yeet" / "artifacts" / run_id
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if d.is_dir())


def _expand(base: Path, pattern: str) -> list[Path]:
    """Glob `pattern` under `base`, or take it literally if it is a plain path.

    An absolute pattern is resolved as given; `Path.glob` refuses one.
    """
    text = pattern.strip()
    if not text:
        return []
    candidate = Path(text)
    if candidate.is_absolute():
        return [candidate] if candidate.exists() else []
    if not any(ch in text for ch in "*?["):
        target = base / text
        if target.is_dir():
            return [p for p in sorted(target.rglob("*")) if p.is_file()]
        return [target] if target.exists() else []
    # `dist/**` means "everything under dist" to GitHub. To Python's glob a
    # trailing `**` matches DIRECTORIES only, so the pattern in the most common
    # upload-artifact line in existence would have stored nothing at all.
    if text.endswith("**"):
        text += "/*"
    return sorted(base.glob(text))


def _relative(path: Path, base: Path) -> Path:
    try:
        return path.resolve().relative_to(base.resolve())
    except ValueError:
        return Path(path.name)
