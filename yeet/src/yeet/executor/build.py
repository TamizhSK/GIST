"""docker build for a project Dockerfile. Tag = hash(dockerfile + context) = free cache.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def build_tag(dockerfile: Path) -> str:
    raise NotImplementedError
