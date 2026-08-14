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

# Glyphs — plain ASCII on purpose (oh-my-zsh's ASCII-safe themes, not its
# Unicode/Powerline ones): a run has to look right on a legacy Windows
# console codepage as much as on a UTF-8 terminal, and there is no ASCII
# glyph so unsafe it needs a font.
SYMBOL_PASS: Final[str] = "[OK]"
SYMBOL_FAIL: Final[str] = "[FAIL]"
SYMBOL_SKIP: Final[str] = "[SKIP]"
SYMBOL_RUNNING: Final[str] = ">"
SYMBOL_BULLET: Final[str] = "*"

# Tree-drawing, ASCII-art style — the same four glyphs `tree --charset ascii`
# uses. Shared between `reporting.console` (which only ever uses BRANCH; it
# prints one line at a time and never learns in advance which step is last)
# and `reporting.live` (which holds the whole job in memory and can tell).
BRANCH: Final[str] = "+-- "
LAST_BRANCH: Final[str] = "\\-- "
PIPE: Final[str] = "|   "
BLANK: Final[str] = "    "


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


def format_summary(
    workflow_name: str,
    status: str,
    duration_s: float,
    *,
    run_id: str = "",
    job_count: int = 0,
    color: bool = True,
) -> str:
    """The one final-line format, shared by `RunConsole` and the live renderer
    (`reporting.live`) so a run looks the same whether it was piped or watched
    live — bullet 5 of the rework asked for "styled consistently with the rest"
    and the only way to guarantee that is one function, not two that agree by
    convention.

    `status` is a `core.result.Status` value (`"slayed"`, `"flopped"`, ...),
    not `STATUS_SKIPPED`'s display text — this only ever renders a run's
    overall status, and a run is never "skipped".
    """
    if status == STATUS_SLAYED:
        icon, code = SYMBOL_PASS, Colors.BOLD + Colors.GREEN
    elif status == STATUS_FLOPPED:
        icon, code = SYMBOL_FAIL, Colors.BOLD + Colors.RED
    else:
        icon, code = SYMBOL_RUNNING, Colors.BOLD + Colors.YELLOW

    status_str = colorize(f"{icon} {status.upper()}", code, color=color)

    detail = []
    if job_count:
        detail.append(f"{job_count} job(s)")
    if run_id:
        detail.append(f"run {run_id}")
    suffix = f" ({', '.join(detail)})" if detail else ""

    return f"\nflow: {workflow_name} - {status_str} in {duration_s:.1f}s{suffix}"
