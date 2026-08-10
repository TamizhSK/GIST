"""analyze(path) -> Project. The public face of this package.

The `Project` dataclass itself lives in `core.project`, not here: `reporting`
formats one for `yeet scan` and tier 1 may not import tier 2.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.project import Project


def analyze(start: Path) -> Project:
    """Root detection -> discovery -> fingerprint. See architecture.md 3.9.

    Touches the filesystem only. No YAML is parsed at this stage — that is the
    parser's job, and keeping the split means `yeet scan` stays fast on repos
    with a hundred workflow files.
    """
    raise NotImplementedError
