"""Runtime config + per-platform paths (platformdirs). Loaded once, passed down.

Owner: Dev D
Tier: 0 — may import from: nothing (core is a leaf)
See docs/architecture.md
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import platformdirs
except ImportError:
    platformdirs = None  # type: ignore[assignment]


def home_dir() -> Path | None:
    """`$HOME`, or None when the environment does not say.

    A git hook, cron and Task Scheduler all run with a stripped environment,
    and `Path.home()` RAISES rather than guessing when neither `USERPROFILE`
    nor `HOMEDRIVE`+`HOMEPATH` is set. Callers use home as a stopping point for
    an upward walk, so None means "walk further" — not a traceback in front of
    a user who ran `git commit`.
    """
    try:
        return Path.home().resolve()
    except (RuntimeError, OSError):
        return None


def config_dir() -> Path:
    """~/.config/yeet, %APPDATA%\\yeet, ~/Library/... — use platformdirs."""
    if platformdirs is not None:
        return Path(platformdirs.user_config_dir("yeet", appauthor=False))
    # Fallback if platformdirs unavailable
    home = home_dir() or Path.cwd()
    if sys.platform == "win32":
        return home / "AppData" / "Roaming" / "yeet"
    return home / ".config" / "yeet"


def cache_dir() -> Path:
    """Keep this SHALLOW on Windows: %LOCALAPPDATA%\\yeet, not a deep nest.
    Paths over 260 chars still break tooling there.
    """
    if platformdirs is not None:
        return Path(platformdirs.user_cache_dir("yeet", appauthor=False))
    home = home_dir() or Path.cwd()
    if sys.platform == "win32":
        return home / "AppData" / "Local" / "yeet"
    return home / ".cache" / "yeet"


def load_lint_config(root: Path) -> dict[str, str]:
    """Read .yeet/lint.yml -> {"YEET-W403": "error", "YEET-W407": "off"}.

    Missing file is not an error — return {}. Layer 4 applies these as severity
    overrides so a team can promote or silence any rule.
    """
    cfg_file = root / ".yeet" / "lint.yml"
    if not cfg_file.exists():
        cfg_file = root / ".yeet" / "lint.yaml"
    if not cfg_file.exists():
        return {}

    result: dict[str, str] = {}
    try:
        content = cfg_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            rule_code = k.strip().upper()
            sev_val = v.strip().lower()
            if not rule_code.startswith("YEET-"):
                rule_code = f"YEET-{rule_code}"
            result[rule_code] = sev_val
    except Exception:
        pass

    return result
