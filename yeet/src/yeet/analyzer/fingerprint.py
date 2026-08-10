"""Detect the stack from marker files so we can pick an image / generate a flow.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def fingerprint(root: Path) -> list["Ecosystem"]:
    raise NotImplementedError
