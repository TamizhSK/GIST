"""Runtime config + per-platform paths (platformdirs). Loaded once, passed down.

Owner: Dev D
Tier: 0 — may import from: nothing (core is a leaf)
See docs/architecture.md
"""
from __future__ import annotations

def config_dir() -> Path:
    """~/.config/yeet, %APPDATA%\\yeet, ~/Library/... — use platformdirs."""
    raise NotImplementedError
