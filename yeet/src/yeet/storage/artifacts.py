"""loot: upload/download -> .yeet/artifacts/<run-id>/.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import shutil
from pathlib import Path


def store_artifact(root: Path, run_id: str, name: str, source_path: Path) -> Path | None:
    """Store an artifact under `.yeet/artifacts/<run-id>/<name>/`."""
    if not source_path.exists():
        return None

    dest_dir = root / ".yeet" / "artifacts" / run_id / name
    dest_dir.mkdir(parents=True, exist_ok=True)

    if source_path.is_file():
        dest = dest_dir / source_path.name
        shutil.copy2(source_path, dest)
        return dest
    elif source_path.is_dir():
        shutil.copytree(source_path, dest_dir, dirs_exist_ok=True)
        return dest_dir

    return None


def list_artifacts(root: Path, run_id: str) -> list[Path]:
    """List all artifact directories for a given run ID."""
    artifacts_dir = root / ".yeet" / "artifacts" / run_id
    if not artifacts_dir.exists():
        return []
    return [d for d in artifacts_dir.iterdir() if d.is_dir()]
