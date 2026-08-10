"""Filter EVERY output line. Mask base64 and url-encoded variants too.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""
from __future__ import annotations

def mask(line: str, secrets: set[str]) -> str:
    raise NotImplementedError
