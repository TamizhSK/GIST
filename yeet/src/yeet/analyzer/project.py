"""Project dataclass + analyze(path) -> Project. The public face of this package.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def analyze(start: Path) -> "Project":
    """Root detection -> discovery -> fingerprint. See architecture.md 3.9."""
    raise NotImplementedError
