"""THE cross-platform helper. C:\\x -> /c/x. Unit-test this on all 3 OSes.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def to_container_path(host: Path) -> str:
    raise NotImplementedError
