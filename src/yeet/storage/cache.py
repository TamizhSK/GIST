"""keyed tarballs + restore-keys PREFIX matching.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md

The prefix in "restore-keys prefix matching" is the entire feature, and the
first implementation did not have it: it hashed each restore key and looked for
that exact hash on disk. Hashing destroys prefixes — `node-` and
`node-abc123` share no bytes once they are SHA-256'd — so a restore key could
only ever hit when it exactly equalled the key that saved the entry, which is
the one case restore keys are not for.

Entries are therefore stored under a name that keeps the key readable, with a
short hash appended only to make it path-safe and collision-resistant:

    <cache-dir>/cache/<slug>-<hash8>.tar
    <cache-dir>/cache/<slug>-<hash8>.key    # the exact key, verbatim

The `.key` sidecar is what prefix matching reads, so matching is done against
the real key and never against a lossy filename.
"""

from __future__ import annotations

import hashlib
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

from yeet.core.config import cache_dir

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_SLUG_MAX = 60


@dataclass(frozen=True, slots=True)
class CacheHit:
    """Which key actually matched. `exact` is False for a restore-key hit.

    GitHub exposes this as `steps.<id>.outputs.cache-hit`, and workflows branch
    on it — `if: steps.cache.outputs.cache-hit != 'true'` around an install
    step is the single most common cache idiom there is.
    """

    key: str
    path: Path
    exact: bool


def entry_path(key: str) -> Path:
    """Where `key` is stored. Readable prefix + hash for uniqueness."""
    slug = _UNSAFE.sub("-", key).strip("-")[:_SLUG_MAX] or "key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return _store() / f"{slug}-{digest}.tar"


def save_cache(key: str, paths: list[Path], *, base: Path) -> Path | None:
    """Tar `paths` under `key`. Returns the tarball, or None if nothing existed.

    Members are stored RELATIVE TO `base` (the workspace), so a restore puts
    `node_modules/` back where it came from. The first version used
    `arcname=p.name`, which flattens: `src/dist` and `web/dist` both became
    `dist`, and restoring either wrote over the other in the workspace root.
    """
    present = [p for p in paths if p.exists()]
    if not present:
        return None

    tar_path = entry_path(key)
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tar_path.with_suffix(".tar.part")
    try:
        with tarfile.open(tmp, "w") as tar:
            for path in present:
                tar.add(path, arcname=_arcname(path, base))
        tmp.replace(tar_path)
        tar_path.with_suffix(".key").write_text(key, encoding="utf-8")
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return tar_path


def restore_cache(key: str, restore_keys: list[str] | None, *, dest: Path) -> CacheHit | None:
    """Exact key first, then each restore key as a PREFIX, newest match wins.

    Returns the hit so the caller can report `cache-hit: true|false` — an exact
    hit and a prefix hit are different answers and workflows branch on which.
    """
    exact = entry_path(key)
    if exact.is_file():
        _extract(exact, dest)
        return CacheHit(key=key, path=exact, exact=True)

    for prefix in restore_keys or []:
        match = _newest_with_prefix(prefix)
        if match is not None:
            tar_path, matched_key = match
            _extract(tar_path, dest)
            return CacheHit(key=matched_key, path=tar_path, exact=False)
    return None


def _newest_with_prefix(prefix: str) -> tuple[Path, str] | None:
    """The most recently written entry whose REAL key starts with `prefix`.

    Reads the `.key` sidecar rather than the filename: the filename is slugged
    and truncated, so `feat/x` and `feat-x` share one slug and a filename match
    would restore the wrong cache.
    """
    candidates: list[tuple[float, Path, str]] = []
    for sidecar in _store().glob("*.key"):
        try:
            stored = sidecar.read_text(encoding="utf-8")
        except OSError:
            continue
        tar_path = sidecar.with_suffix(".tar")
        if stored.startswith(prefix) and tar_path.is_file():
            candidates.append((tar_path.stat().st_mtime, tar_path, stored))
    if not candidates:
        return None
    _, tar_path, stored = max(candidates, key=lambda item: item[0])
    return tar_path, stored


def _extract(tar_path: Path, dest: Path) -> None:
    """`filter="data"` is not optional.

    A tarball is attacker-controlled input the moment a cache directory is
    shared or restored from a branch someone else pushed, and the default
    extraction happily follows `../../..` out of `dest`. Python 3.12 warns
    about this and 3.14 changes the default; naming it here means the
    behaviour does not depend on which interpreter a user happens to run.
    """
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r") as tar:
        try:
            tar.extractall(path=dest, filter="data")
        except TypeError as exc:
            # The `filter` argument was backported to 3.9.17 / 3.10.12 /
            # 3.11.4; an older patch release of a version we otherwise support
            # raises TypeError here. Refuse rather than retry without it —
            # falling back silently is how a security fix becomes optional, and
            # a cache that will not restore is a far smaller problem than an
            # archive that writes outside the workspace.
            raise RuntimeError(
                "this Python is too old to extract archives safely "
                f"({exc}). Upgrade to 3.10.12+, 3.11.4+, or any 3.12+."
            ) from exc


def _arcname(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        # Outside the workspace (`~/.npm`, an absolute path). Store it by name;
        # restoring it into the workspace root is the best available answer.
        return path.name


def _store() -> Path:
    return cache_dir() / "cache"
