"""Colors, glyphs, the status vocabulary. Honor NO_COLOR.

The palette is the wordmark's. `tools/gen_logo.py` samples GTA VI's sunset
down twelve rows of block art — indigo at the top of the word, magenta through
the middle, a low sun at the baseline — and `SUNSET_STOPS` below is that same
table, so the terminal and `assets/yeet.svg` are tinted from one gradient
rather than two that happen to look alike. `tests/unit/test_reporting.py`
asserts the two tables are still identical; they are duplicated rather than
imported because `tools/` is not a package and `reporting` is tier 1.

The gradient is mapped onto the run's HIERARCHY, top to bottom, the same way it
is mapped onto the letters: a job header is the indigo at the top of the
wordmark, a step name is the magenta through its middle, and whatever is
running right now is the lit sun at its baseline. So the tree reads as the logo
does, and the eye can find the live row without reading a word of it.

Status is the one thing that does NOT come from the gradient. A sunset has no
green, and "did it pass" is the question the colour is there to answer — pass,
fail and skip keep the conventional green/red/grey (the same three the
installer uses) so they mean what they have always meant, and only their exact
tones are picked to sit beside the sunset without clashing.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import enum
import functools
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Final, TextIO

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
SYMBOL_WARN: Final[str] = "[!]"
SYMBOL_NOTE: Final[str] = "note:"
SYMBOL_ARROW: Final[str] = "->"
SYMBOL_FROM: Final[str] = "<-"

# Everything above is 7-bit ASCII, and that is the whole requirement: these
# reach a legacy Windows console (cp437/cp1252), an ssh session with no locale,
# a CI log viewer, and a `yeet run > out.txt` opened in any editor. A `✔` or a
# `📦` is one `UnicodeEncodeError` away from taking down the command that was
# only trying to tell you something — and on the consoles that CAN print them,
# they are usually the wrong width, which breaks every aligned column after.
#
# `reporting.live` may use box characters because it has already established
# that it is talking to a real terminal; nothing in `cli/` may.

# Tree-drawing, ASCII-art style — the same four glyphs `tree --charset ascii`
# uses. Shared between `reporting.console` (which only ever uses BRANCH; it
# prints one line at a time and never learns in advance which step is last)
# and `reporting.live` (which holds the whole job in memory and can tell).
BRANCH: Final[str] = "+-- "
LAST_BRANCH: Final[str] = "\\-- "
PIPE: Final[str] = "|   "
BLANK: Final[str] = "    "

# Panel-drawing. Unlike the tree glyphs above — which stay ASCII because they
# are printed on EVERY line, including into logs that get read back on a
# machine we know nothing about — the panel is drawn once, at the end, and it
# is the last thing the user looks at. So it takes the box characters when the
# stream can encode them and falls back to `+ - |` when it cannot.
#
# Asked of the stream rather than of `LANG`: a UTF-8 locale piped into a file
# opened as cp1252 still raises, and the encoding the bytes will actually be
# written with is the only thing that answers the question.
_PANEL_UNICODE = ("\u256d", "\u256e", "\u2570", "\u256f", "\u2500", "\u2502", "\u00b7")
_PANEL_ASCII = ("+", "+", "+", "+", "-", "|", "*")


def panel_glyphs(stream: TextIO | None = None) -> tuple[str, str, str, str, str, str, str]:
    """`(tl, tr, bl, br, horizontal, vertical, bullet)` this stream can print."""
    target = stream if stream is not None else sys.stdout
    encoding = getattr(target, "encoding", None) or "ascii"
    try:
        "".join(_PANEL_UNICODE).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return _PANEL_ASCII
    return _PANEL_UNICODE


PANEL_CORNER: Final[str] = "+"
PANEL_H: Final[str] = "-"
PANEL_V: Final[str] = "|"
PANEL_WIDTH: Final[int] = 70
"""Inner width of the summary panel, matching the installer's `W=70`."""
PANEL_MIN_WIDTH: Final[int] = 34
"""Below this there is no panel worth drawing — the summary degrades to its
one plain line rather than printing a frame with a ragged right edge."""


# --- capability -------------------------------------------------------------


class ColorLevel(enum.IntEnum):
    """How much colour the destination can actually take.

    Ordered, so `level >= ColorLevel.ANSI256` is a legal question to ask. The
    two interesting members are the ends: NONE is a pipe, a `NO_COLOR`
    environment or `TERM=dumb`, and it must produce byte-for-byte plain text,
    not "colour that happens to be off".
    """

    NONE = 0
    BASIC = 1
    """The original eight, plus their bright forms. Everything must survive here."""
    ANSI256 = 2
    TRUECOLOR = 3


@functools.lru_cache(maxsize=8)
def _tput_colors(term: str) -> int:
    """`tput colors` for a TERM, asked at most once per process per TERM.

    The last resort, and only reached when TERM says nothing useful — the
    answer costs a fork, and a renderer that forked once per line would be a
    performance bug wearing a feature's clothes. Anything at all going wrong
    (no terminfo, no `tput`, a hang, junk on stdout) is answered as 16, which
    is the level every terminal in this branch has already proven it has by
    setting a TERM that is not `dumb`.
    """
    if not term or term == "dumb":
        return 0
    try:
        out = subprocess.run(
            ["tput", "colors"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
            env={**os.environ, "TERM": term},
        )
        return int(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 16


def color_level(stream: TextIO | None = None, *, enabled: bool = True) -> ColorLevel:
    """What `stream` can take, detected rather than assumed.

    The order of the gates is the whole point. `NO_COLOR` is the user's
    environment speaking and wins over everything, including `FORCE_COLOR`
    (https://no-color.org asks that its mere presence be sufficient).
    `enabled=False` is `--no-color`, which is us speaking on the user's behalf.
    Then the terminal has to exist at all, and `TERM=dumb` is a terminal saying
    it is not one.

    Only after all of that do we ask how MUCH: `COLORTERM` is the only reliable
    signal for truecolour, a TERM containing `256color` is the conventional one
    for 256, and `tput colors` is the fallback for a TERM that advertises
    neither — a plain `xterm` on a modern box usually answers 256, and
    believing its name instead would cost the palette for no reason.
    """
    if os.environ.get("NO_COLOR"):
        return ColorLevel.NONE
    if not enabled:
        return ColorLevel.NONE

    # FORCE_COLOR is set by CI systems that pipe our stdout but render ANSI in
    # their web log viewer. It answers "is there a terminal", never "how good
    # is it" — the depth below is still detected, never assumed.
    force = os.environ.get("FORCE_COLOR")
    if force == "0":
        return ColorLevel.NONE
    if force is None and not is_tty(stream):
        return ColorLevel.NONE

    term = os.environ.get("TERM", "")
    if term == "dumb":
        return ColorLevel.NONE

    colorterm = os.environ.get("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return ColorLevel.TRUECOLOR
    if "256color" in term or "256" in colorterm:
        return ColorLevel.ANSI256

    count = _tput_colors(term)
    if count >= 256:
        return ColorLevel.ANSI256
    if count >= 8:
        return ColorLevel.BASIC
    return ColorLevel.NONE


def is_tty(stream: TextIO | None = None) -> bool:
    """True only for a real terminal. A pipe, a redirect and a closed stream
    are all False, and a stream that lies about having `isatty` is False too."""
    stream = stream if stream is not None else sys.stdout
    try:
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())
    except (OSError, ValueError):  # a closed file object raises here
        return False


def use_color(stream: TextIO | None = None) -> bool:
    """Return True if colored output should be enabled."""
    return color_level(stream) is not ColorLevel.NONE


# --- the sunset -------------------------------------------------------------

# Mirrors `STOPS` in tools/gen_logo.py. Three values of one hue per stop: what
# fills a cell of the wordmark, what its shade characters are drawn in, and
# what its bevel is drawn in.
#                     position   mid        light      deep
SUNSET_STOPS: Final[tuple[tuple[float, str, str, str], ...]] = (
    (0.00, "#3b41a8", "#5f68d8", "#2b2f80"),
    (0.22, "#5a3fae", "#7f60d8", "#432c84"),
    (0.44, "#9445a0", "#b96ac0", "#6f3079"),
    (0.62, "#c1517f", "#e07aa4", "#933a60"),
    (0.80, "#dc6f58", "#f2977c", "#a85440"),
    (1.00, "#e89a4e", "#ffc07d", "#b57334"),
)


def _mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    mr = round(ar + (br - ar) * t)
    mg = round(ag + (bg - ag) * t)
    mb = round(ab + (bb - ab) * t)
    return f"#{mr:02x}{mg:02x}{mb:02x}"


def sunset(position: float) -> tuple[str, str, str]:
    """(mid, light, deep) at `position` down the wordmark, 0..1 — the same
    function `tools/gen_logo.py` samples once per row of block art."""
    for i in range(len(SUNSET_STOPS) - 1):
        lo, *lo_tones = SUNSET_STOPS[i]
        hi, *hi_tones = SUNSET_STOPS[i + 1]
        if lo <= position <= hi:
            t = 0.0 if hi == lo else (position - lo) / (hi - lo)
            mixed = tuple(_mix(a, b, t) for a, b in zip(lo_tones, hi_tones, strict=True))
            return mixed[0], mixed[1], mixed[2]
    last = SUNSET_STOPS[-1]
    return last[1], last[2], last[3]


# --- legible on a dark theme AND a light one --------------------------------
#
# A terminal does not tell us its background colour. There is no portable query
# for it: `COLORFGBG` is set by a minority of emulators, is not updated when
# the user switches theme inside a running session, and a STALE answer is worse
# than no answer — it would confidently pick the tones that vanish. So the
# palette is not tuned per theme; every tone is picked to be readable against
# both, which is the same decision `tools/gen_logo.py` made for the wordmark
# ("every tone is a mid-to-light value that holds against white as well as
# against near-black") and the reason the logo sits on either GitHub theme.
#
# That decision has an exact form. WCAG contrast against a background of
# relative luminance B is (L+0.05)/(B+0.05), so requiring 3:1 against a dark
# terminal AND against a white one traps L in a band:
#
#     L >= 3*(0.012 + 0.05) - 0.05  = 0.139     (readable on #1e1e1e)
#     L <= 1.05/3 - 0.05            = 0.300     (readable on #ffffff)
#
# It is a narrow band and it is not negotiable: outside it, one half of the
# world cannot read the output. 4.5:1 on both is arithmetically impossible for
# any colour at all (the best any single tone can do against pure black and
# pure white at once is 4.58:1, at L=0.179), which is worth knowing before
# anyone tries to "fix" these values by brightening them.
#
# What the band costs is absolute brightness; what it keeps is ORDER. Hierarchy
# is carried by where a tone sits WITHIN the band — the running spinner at the
# top of it, our own muted notes at the bottom — plus bold, which no palette
# can take away. `tests/unit/test_reporting.py::test_every_ink_is_legible_on_
# dark_and_light_terminals` holds the line against six real terminal
# backgrounds.

LUMA_FLOOR: Final[float] = 0.139
LUMA_CEILING: Final[float] = 0.300

REFERENCE_BACKGROUNDS: Final[tuple[str, ...]] = (
    "#000000",  # a plain black terminal
    "#1e1e1e",  # VS Code Dark, and roughly every "dark" default
    "#002b36",  # Solarized Dark
    "#ffffff",  # a plain white terminal
    "#fafafa",  # macOS Terminal "Basic"
    "#fdf6e3",  # Solarized Light
)
"""What "both themes" means concretely, so the claim can be tested."""


def luminance(hexcolor: str) -> float:
    """WCAG relative luminance, 0..1."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours, 1..21."""
    la, lb = luminance(a), luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def _scaled(hexcolor: str, k: float) -> str:
    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))
    cr, cg, cb = (min(255, max(0, round(v * k))) for v in (r, g, b))
    return f"#{cr:02x}{cg:02x}{cb:02x}"


def legible(hexcolor: str, target: float) -> str:
    """The same hue, moved to a value that clears both themes.

    Scaling all three channels together holds the chromaticity — the result is
    still recognisably the wordmark's indigo or its low sun, just at a value
    that survives a white background. Picking a replacement colour by eye
    instead is how a palette ends up with one tone that is legible and five
    that were only ever checked against the picker's own terminal.
    """
    lo, hi = 0.0, 8.0
    for _ in range(32):  # luminance is monotonic in k, so bisection converges
        k = (lo + hi) / 2
        if luminance(_scaled(hexcolor, k)) < target:
            lo = k
        else:
            hi = k
    return _scaled(hexcolor, (lo + hi) / 2)


_CUBE: Final[tuple[int, ...]] = (0, 95, 135, 175, 215, 255)


def to_ansi256(hexcolor: str) -> int:
    """Nearest xterm-256 index to a hex colour.

    Computed rather than a table of hand-picked indices, because the hexes
    above are the ones that can change (they come from the logo) and a
    hand-picked index would silently stop matching the colour it was picked
    for. Both the 6x6x6 cube and the 24-step grey ramp are candidates: a
    desaturated tone like the gutter's is several shades closer in the greys.
    """
    r, g, b = (int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))

    def nearest(v: int) -> int:
        return min(range(6), key=lambda i: abs(_CUBE[i] - v))

    ri, gi, bi = nearest(r), nearest(g), nearest(b)
    cube_dist = (_CUBE[ri] - r) ** 2 + (_CUBE[gi] - g) ** 2 + (_CUBE[bi] - b) ** 2

    grey_i = min(range(24), key=lambda i: abs((8 + 10 * i) - (r + g + b) // 3))
    grey = 8 + 10 * grey_i
    grey_dist = (grey - r) ** 2 + (grey - g) ** 2 + (grey - b) ** 2

    if grey_dist < cube_dist:
        return 232 + grey_i
    return 16 + 36 * ri + 6 * gi + bi


_ATTR_SGR: Final[dict[str, str]] = {"bold": "1", "dim": "2", "italic": "3", "underline": "4"}
_BASIC_SGR: Final[dict[str, str]] = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
}


@dataclass(frozen=True)
class Ink:
    """One semantic colour, expressed once and rendered at whatever depth the
    terminal turned out to have.

    `basic` is hand-picked rather than derived: the eight ANSI colours are
    whatever the user's theme says they are, so "nearest to #b96ac0" is not a
    question with an answer in RGB — the right fallback for the wordmark's
    magenta is the terminal's own idea of magenta, wherever that lands. They
    are also the NON-bright eight throughout, because those are the entries a
    light theme darkens and a dark theme brightens; `bright_yellow` on white is
    the one every 16-colour palette gets wrong.

    Renders to an SGR escape for the hand-written renderers and to a `rich`
    style string for the live tree, from the same definition, so the two cannot
    drift apart the way two colour tables always eventually do.
    """

    hex: str
    """Empty for an ink that is attributes only — see `BOLD`."""
    basic: str
    """Empty means "do not set a colour at all" — the right answer for our
    greys, whose 16-colour spelling is `dim` on the user's own foreground.
    Naming `white` there would be white-on-white on a light terminal."""
    attrs: tuple[str, ...] = ()
    basic_attrs: tuple[str, ...] = ()
    """Attributes added only once there is no colour left to spend. `dim` is
    the case: on top of an explicit mid-grey it just makes it harder to read,
    but with no colour at all it is the only way left to say "subordinate"."""

    @functools.cached_property
    def index256(self) -> int:
        return to_ansi256(self.hex)

    def sgr(self, level: ColorLevel) -> str:
        if level is ColorLevel.NONE:
            return ""
        parts = [_ATTR_SGR[a] for a in self._attrs(level)]
        if not self.hex:
            pass
        elif level is ColorLevel.TRUECOLOR:
            r, g, b = (int(self.hex[i : i + 2], 16) for i in (1, 3, 5))
            parts.append(f"38;2;{r};{g};{b}")
        elif level is ColorLevel.ANSI256:
            parts.append(f"38;5;{self.index256}")
        elif self.basic:
            parts.append(_BASIC_SGR[self.basic])
        if not parts:
            return ""
        return "\033[" + ";".join(parts) + "m"

    def rich(self, level: ColorLevel) -> str:
        """The same colour as a `rich` style string.

        Resolved here instead of handing rich the hex and letting it downgrade,
        so that a terminal this module decided was 16-colour gets 16-colour
        from BOTH renderers. Two capability detectors disagreeing is how you
        get a live tree in truecolour and a summary line in blue.
        """
        if level is ColorLevel.NONE:
            return ""
        parts = list(self._attrs(level))
        if not self.hex:
            pass
        elif level is ColorLevel.TRUECOLOR:
            parts.append(self.hex)
        elif level is ColorLevel.ANSI256:
            parts.append(f"color({self.index256})")
        elif self.basic:
            parts.append(self.basic)
        return " ".join(parts)

    def _attrs(self, level: ColorLevel) -> tuple[str, ...]:
        if level >= ColorLevel.ANSI256:
            return self.attrs
        return self.attrs + self.basic_attrs


class Ansi:
    """Escape codes that are not colours."""

    RESET: Final[str] = "\033[0m"


# The wordmark, read top to bottom, mapped onto the run read top to bottom.
# The second argument to `legible` is where the tone sits in the band, and that
# ORDER is the hierarchy: running at the ceiling, our own asides at the floor.
JOB: Final[Ink] = Ink(legible(sunset(0.05)[1], 0.175), "blue", ("bold",))
"""Indigo, the top row of the block letters. Low in the band because indigo has
nowhere else to go — a blue bright enough to sit at 0.29 is no longer indigo,
it is sky — so the job header leans on bold for its weight instead."""
STEP: Final[Ink] = Ink(legible(sunset(0.44)[1], 0.235), "magenta")
"""Magenta, the middle of the word."""
GUTTER: Final[Ink] = Ink(legible(sunset(0.25)[1], 0.185), "blue")
"""The `job |` attribution column: violet, between the two, and deliberately
un-dimmed. It was DIM before, which on a low-contrast terminal theme made the
one piece of text whose entire job is to be readable at a glance the least
readable thing on the line."""
RUNNING: Final[Ink] = Ink(legible(sunset(0.98)[1], 0.290), "yellow", ("bold",))
"""The lit sun at the baseline — the spinner, and the `>` that marks the row a
plain console is currently filling in. At the top of the band, so the thing
that is happening is the brightest thing on screen that a light terminal can
still show."""
ACCENT: Final[Ink] = Ink(legible(sunset(1.00)[0], 0.260), "yellow")
"""The low sun's solid tone: the summary panel's frame, and the run's label."""

# Status. Not from the gradient — see the module docstring — but held to the
# same band, which is why they are mid green and mid red rather than the
# #87d787/#ff5f5f the installer can afford on its own first screen.
PASS: Final[Ink] = Ink(legible("#87d787", 0.270), "green", ("bold",))
FAIL: Final[Ink] = Ink(legible("#ff5f5f", 0.215), "red", ("bold",))
SKIP: Final[Ink] = Ink(legible("#8a8a8a", 0.200), "", (), ("dim",))
WARN: Final[Ink] = Ink(legible("#ffd75f", 0.265), "yellow")
INFO: Final[Ink] = Ink(legible(sunset(0.20)[1], 0.190), "blue")
"""Advisory, not a verdict: the wordmark's upper indigo, used for a `note` and
for the code frame's gutter."""

# Output. A step's own stdout is left in the terminal's foreground colour on
# the plain console: it is the user's program talking, not ours, and tinting it
# would be the decoration this palette is trying not to be — and it is the one
# colour guaranteed to suit whatever background the user chose.
STDERR: Final[Ink] = Ink(legible(sunset(0.80)[1], 0.250), "red")
"""Warm, and a shade off FAIL's red on purpose. stderr is a STREAM, not a
verdict — plenty of correct programs log to it — so it reads as "look here",
while `[FAIL]` alone reads as "this broke"."""
META: Final[Ink] = Ink(legible("#9a92b0", 0.175), "", ("italic",), ("dim",))
"""Our own notes inside a step (skipped/timed-out/degraded reasons)."""
MUTE: Final[Ink] = Ink(legible("#9e9e9e", 0.160), "", (), ("dim",))
"""Tailed stdout under the live tree, and the panel's detail row."""
BOLD: Final[Ink] = Ink("", "", ("bold",))
"""Emphasis with no colour of its own. Deliberately not white: half the world
runs a light terminal theme, and `#ffffff` on it is invisible — the foreground
the user already chose is the only colour guaranteed to be readable against
the background they chose with it."""


def ink_for_status(status: str | None) -> tuple[str, Ink]:
    """`(glyph, ink)` for a `core.result.Status` value — `"slayed"`,
    `"flopped"`, `"skipped"`, `"cancelled"`, or `None`/anything unrecognised,
    which a report must render rather than crash over."""
    if status == STATUS_SLAYED:
        return SYMBOL_PASS, PASS
    if status == STATUS_FLOPPED:
        return SYMBOL_FAIL, FAIL
    if status in ("skipped", "cancelled"):
        return SYMBOL_SKIP, SKIP
    return SYMBOL_RUNNING, RUNNING


# --- painting ---------------------------------------------------------------


def paint(text: str, ink: Ink, *, level: ColorLevel) -> str:
    """Wrap `text` in `ink` at `level`. Plain text at ColorLevel.NONE."""
    code = ink.sgr(level)
    if not code:
        return text
    return f"{code}{text}{Ansi.RESET}"


# ANSI Color codes — the original 16, kept because `reporting.render` builds
# code-frame colours by concatenating them and because they are the honest
# spelling of a fallback.
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


# --- the summary ------------------------------------------------------------


def _panel_width(width: int | None) -> int:
    """Fit the terminal or do not draw a box at all — the installer's rule.

    A fixed frame wider than the window does not look like a wide box, it looks
    like corruption: every row wraps and the right border lands under the left
    one.
    """
    columns = width if width is not None else shutil.get_terminal_size(fallback=(80, 24)).columns
    # Capped, not just fitted. A caller passing the console width means "this
    # is the room you have", not "fill it": a 111-column frame around two short
    # rows is mostly empty box, and the eye has to travel the whole width to
    # find out nothing is there.
    return min(PANEL_WIDTH, columns - 2)


def format_summary(
    workflow_name: str,
    status: str,
    duration_s: float,
    *,
    run_id: str = "",
    job_count: int = 0,
    level: ColorLevel | None = None,
    panel: bool = False,
    width: int | None = None,
    stream: TextIO | None = None,
) -> str:
    """The one final-line format, shared by `RunConsole` and the live renderer
    (`reporting.live`) so a run looks the same whether it was piped or watched
    live — bullet 5 of the rework asked for "styled consistently with the rest"
    and the only way to guarantee that is one function, not two that agree by
    convention.

    `panel` asks for the framed block that closes an interactive run, the
    counterpart to the one the installer prints when it finishes. It is a
    request and not a promise: a window too narrow to frame gets the plain
    line, because a box with a ragged right edge says "this tool is broken"
    more loudly than the summary says anything at all. The caller passes
    `panel=False` whenever stdout is not a terminal, where a frame is not
    wrong so much as pointless — nothing downstream of a pipe wants ASCII art
    around one fact.

    `status` is a `core.result.Status` value (`"slayed"`, `"flopped"`, ...),
    not `STATUS_SKIPPED`'s display text — this only ever renders a run's
    overall status, and a run is never "skipped".

    `stream` is THE stream this text is about to be written to, and it must be
    the caller's own. The box glyphs are chosen by asking what can be encoded,
    and the default — `sys.stdout` — is the wrong stream whenever the caller
    writes anywhere else. `RunConsole(out=...)` does exactly that, so a
    `yeet run > out.txt` on a cp1252 machine picked the Unicode box by asking
    the console and then raised `UnicodeEncodeError` writing it to the file:
    the encoding gate was real, and pointed at the wrong thing.
    """
    if level is None:
        level = color_level()

    icon, ink = ink_for_status(status)
    verdict = f"{icon} {status.upper()}"

    detail = []
    if job_count:
        detail.append(f"{job_count} job(s)")
    if run_id:
        detail.append(f"run {run_id}")

    if panel:
        inner = _panel_width(width)
        if inner >= PANEL_MIN_WIDTH:
            return _summary_panel(
                workflow_name, verdict, duration_s, detail, ink, level, inner, stream
            )

    suffix = f" ({', '.join(detail)})" if detail else ""
    status_str = paint(verdict, ink, level=level)
    return f"\nflow: {workflow_name} - {status_str} in {duration_s:.1f}s{suffix}"


def _summary_panel(
    workflow_name: str,
    verdict: str,
    duration_s: float,
    detail: list[str],
    ink: Ink,
    level: ColorLevel,
    inner: int,
    stream: TextIO | None = None,
) -> str:
    """The framed close. Every row is measured as PLAIN text and coloured
    afterwards, because an ANSI escape is zero columns wide and `len()` of a
    coloured string is the classic way to get a box whose right edge wobbles by
    exactly the length of a colour code.
    """
    tl, tr, bl, br, horizontal, vertical, bullet = panel_glyphs(stream)
    top = paint(tl + horizontal * inner + tr, ACCENT, level=level)
    bottom = paint(bl + horizontal * inner + br, ACCENT, level=level)
    bar = paint(vertical, ACCENT, level=level)

    def row(*cells: tuple[str, Ink | None]) -> str:
        plain = "".join(text for text, _ in cells)
        # Truncate rather than overflow, for the same reason the installer
        # does: one long workflow name must not undo the arithmetic.
        if len(plain) > inner - 4:
            cells = _truncate(cells, inner - 4)
            plain = "".join(text for text, _ in cells)
        body = "".join(paint(text, style, level=level) if style else text for text, style in cells)
        return f"{bar}  {body}{' ' * (inner - 2 - len(plain))}{bar}"

    rows = [
        row((verdict, ink), ("  ", None), (workflow_name, BOLD)),
        row((_fmt_detail(detail, duration_s, bullet), MUTE)),
    ]
    return "\n" + "\n".join([top, *rows, bottom])


def _truncate(
    cells: tuple[tuple[str, Ink | None], ...], budget: int
) -> tuple[tuple[str, Ink | None], ...]:
    """Drop columns from the right until the row fits, ellipsising the one that
    straddles the edge."""
    kept: list[tuple[str, Ink | None]] = []
    for text, style in cells:
        if budget <= 0:
            break
        if len(text) > budget:
            kept.append((text[: max(0, budget - 3)] + "...", style))
            break
        kept.append((text, style))
        budget -= len(text)
    return tuple(kept)


def _fmt_detail(detail: list[str], duration_s: float, bullet: str = SYMBOL_BULLET) -> str:
    parts = [f"{duration_s:.1f}s", *detail]
    return f"  {bullet}  ".join(parts)
