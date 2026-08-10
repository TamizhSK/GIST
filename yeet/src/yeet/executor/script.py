"""Write a step's script to disk. ALWAYS LF — CRLF kills bash in the container.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def write_step_script(text: str, dest: Path) -> None:
    dest.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
