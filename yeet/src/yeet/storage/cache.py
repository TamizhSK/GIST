"""keyed tarballs + restore-keys prefix matching.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

from yeet.core.config import cache_dir


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def save_cache(key: str, paths: list[Path]) -> Path | None:
    """Tarball specified paths and save under cache_dir() / "cache" / <key_hash>.tar."""
    cdir = cache_dir() / "cache"
    cdir.mkdir(parents=True, exist_ok=True)
    tar_path = cdir / f"{_key_hash(key)}.tar"

    try:
        with tarfile.open(tar_path, "w") as tar:
            for p in paths:
                if p.exists():
                    tar.add(p, arcname=p.name)
        return tar_path
    except Exception:
        return None


def restore_cache(
    key: str, restore_keys: list[str] | None = None, dest_dir: Path | None = None
) -> bool:
    """Restore cache tarball matching key or prefix in restore_keys."""
    cdir = cache_dir() / "cache"
    if not cdir.exists():
        return False

    target_dir = dest_dir or Path.cwd()
    tar_path = cdir / f"{_key_hash(key)}.tar"

    if tar_path.exists():
        try:
            with tarfile.open(tar_path, "r") as tar:
                tar.extractall(path=target_dir)
            return True
        except Exception:
            return False

    # Try restore-keys prefix search
    if restore_keys:
        for rkey in restore_keys:
            r_hash = _key_hash(rkey)
            r_tar = cdir / f"{r_hash}.tar"
            if r_tar.exists():
                try:
                    with tarfile.open(r_tar, "r") as tar:
                        tar.extractall(path=target_dir)
                    return True
                except Exception:
                    pass

    return False
