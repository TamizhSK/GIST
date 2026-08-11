"""Colors, glyphs, the status vocabulary. Honor NO_COLOR.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import os
import sys
from typing import Final

# Status Vocabulary
STATUS_SLAYED: Final[str] = "slayed"
STATUS_FLOPPED: Final[str] = "flopped"
STATUS_MID: Final[str] = "mid"
STATUS_COOKED: Final[str] = "cooked"
STATUS_SKIPPED: Final[str] = "skipped (not the vibe)"

# Glyphs
SYMBOL_PASS: Final[str] = "✔"
SYMBOL_FAIL: Final[str] = "✖"
SYMBOL_SKIP: Final[str] = "⊘"
SYMBOL_RUNNING: Final[str] = "●"
SYMBOL_BULLET: Final[str] = "•"


def use_color() -> bool:
    """Return True if colored output should be enabled."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


# ANSI Color codes
class Colors:
    RESET: Final[str] = "\033[0m"
    BOLD: Final[str] = "\033[1m"
    DIM: Final[str] = "\033[2m"
    ITALIC: Final[str] = "\033[3m"
    UNDERLINE: Final[str] = "\033[4m"

    RED: Final[str] = "\033[31m"
    GREEN: Final[str] = "\033[32m"
    YELLOW: Final[str] = "\033[33m"
    BLUE: Final[str] = "\033[34m"
    MAGENTA: Final[str] = "\033[35m"
    CYAN: Final[str] = "\033[36m"
    WHITE: Final[str] = "\033[37m"

    BRIGHT_RED: Final[str] = "\033[91m"
    BRIGHT_GREEN: Final[str] = "\033[92m"
    BRIGHT_YELLOW: Final[str] = "\033[93m"
    BRIGHT_BLUE: Final[str] = "\033[94m"
    BRIGHT_MAGENTA: Final[str] = "\033[95m"
    BRIGHT_CYAN: Final[str] = "\033[96m"


def colorize(text: str, color_code: str, *, color: bool | None = None) -> str:
    """Wrap text in ANSI color codes unless color is disabled."""
    enabled = use_color() if color is None else color
    if not enabled or not color_code:
        return text
    return f"{color_code}{text}{Colors.RESET}"
