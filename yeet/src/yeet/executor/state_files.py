"""GITHUB_ENV / GITHUB_OUTPUT / GITHUB_PATH / GITHUB_STEP_SUMMARY read-back.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""
from __future__ import annotations

def read_back(step_dir: Path) -> dict[str, dict[str, str]]:
    """Each step is a NEW PROCESS. This file dance is the only way state survives."""
    raise NotImplementedError
