"""OS + WSL detection, docker socket discovery, /mnt/c slowness warning.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations


def is_wsl() -> bool:
    """/proc/version contains 'microsoft'."""
    raise NotImplementedError
