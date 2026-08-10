"""Runtime config + per-platform paths (platformdirs). Loaded once, passed down.

Owner: Dev D
Tier: 0 — may import from: nothing (core is a leaf)
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def config_dir() -> Path:
    """~/.config/yeet, %APPDATA%\\yeet, ~/Library/... — use platformdirs."""
    raise NotImplementedError


def cache_dir() -> Path:
    """Keep this SHALLOW on Windows: %LOCALAPPDATA%\\yeet, not a deep nest.
    Paths over 260 chars still break tooling there."""
    raise NotImplementedError


def load_lint_config(root: Path) -> dict[str, str]:
    """Read .yeet/lint.yml -> {"YEET-W403": "error", "YEET-W407": "off"}.

    Missing file is not an error — return {}. Layer 4 applies these as severity
    overrides so a team can promote or silence any rule.
    """
    raise NotImplementedError
