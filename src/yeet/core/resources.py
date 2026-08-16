"""Data files that ship inside the wheel.

Owner: Dev D
Tier: 0 — may import from: nothing (core is a leaf)
See docs/architecture.md

Two files live at the repo root and are needed at RUN time: `Dockerfile.base`,
without which no `ubuntu-latest` job can start, and `docs/rules.md`, which is
what `yeet explain` prints. Both were located by counting `..` from
`__file__` — `parents[3]` reaches the repo root from a checkout and reaches
site-packages' parent from an install, so both silently returned nothing the
moment anyone installed the wheel. `yeet run` then told the user to run `make
image` in a project they had never cloned.

They are force-included into `yeet/_data/` by `pyproject.toml` — copied at
build time from the one real file, so there is nothing to keep in sync.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

_ROOT_PACKAGE = "yeet"
_DATA = "_data"


def packaged_path(name: str) -> Path | None:
    """The installed path of `name`, or None if it did not ship."""
    try:
        entry = resources.files(_ROOT_PACKAGE) / _DATA / name
        if isinstance(entry, Path) and entry.is_file():
            return entry
    except (ModuleNotFoundError, OSError, TypeError):
        pass
    return None


def packaged_text(name: str) -> str | None:
    """`name`'s contents, or None. Works from a zip import too, where there is
    no path to hand back but the bytes are still readable."""
    try:
        entry = resources.files(_ROOT_PACKAGE) / _DATA / name
        return entry.read_text(encoding="utf-8")
    except (ModuleNotFoundError, OSError, TypeError):
        return None
