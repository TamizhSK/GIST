"""What the installer actually puts on a terminal.

Driven through `install.sh --selftest`, which draws the presentation layer and
exits — the real `bar_draw`, the real `warn`, the real wordmark, with none of
the disk work. The alternative is a 35-second install per assertion, which is
the reason this had no test before.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.sh"

# BEFORE the import below, and that ordering is the whole point. `pty_capture`
# imports `fcntl`, `pty` and `termios`, none of which exist on Windows, and a
# module-level import runs during COLLECTION — before any mark is evaluated. A
# `pytestmark = skipif(...)` at the bottom of this block therefore cannot save
# it: the import has already raised, and pytest reports a collection error that
# fails the whole run rather than skipping one file. That is exactly how this
# file went green on macOS and red on all four Windows jobs.
if sys.platform == "win32":  # pragma: no cover - asserted by the Windows matrix
    pytest.skip("install.sh under a pty; Windows has install.ps1", allow_module_level=True)
if not INSTALLER.exists():  # pragma: no cover - a wheel with no repo around it
    pytest.skip("install.sh is not shipped in the package", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support.pty_capture import bar_lines, capture, render  # noqa: E402


def _screen(cols: int, args: list[str] | None = None, env: dict[str, str] | None = None):
    stream = capture([str(INSTALLER), "--selftest", *(args or [])], cols=cols, env=env, timeout=30)
    return stream, [r for r in render(stream) if r.strip()]


@pytest.mark.parametrize("cols", [110, 100, 80, 72, 64, 46, 40])
def test_a_terminal_shows_exactly_one_bar_at_any_width(cols: int) -> None:
    """The bar is drawn in place with `\\r`. Every frame after the first must
    land on the SAME line — the whole point of the design is that the log
    scrolls and the bar does not."""
    _, rows = _screen(cols)
    bars = bar_lines(rows)
    assert len(bars) == 1, f"{len(bars)} bars at {cols} cols:\n" + "\n".join(rows)


@pytest.mark.parametrize("cols", [110, 100, 80, 72, 64, 46, 40])
def test_the_bar_fills_the_window_and_never_wraps_it(cols: int) -> None:
    """Wider than the window is worse than narrower: `\\r` returns to the start
    of the LAST line, so a wrapped bar leaves its own top half stranded on
    screen forever."""
    _, rows = _screen(cols)
    bar = bar_lines(rows)[0]
    assert len(bar) < cols, f"bar is {len(bar)} wide in a {cols}-column window"
    # Two spaces of margin, brackets, a space, `100%` — anything much shorter
    # than the window means the width was not measured at all.
    assert len(bar) >= cols - 12, f"bar is only {len(bar)} of {cols} columns"


def test_the_label_is_shown_when_there_is_room_for_it() -> None:
    """ "Stuck at 63%" is not a bug report. "Stuck at 63% — resolving and
    downloading" is."""
    _, rows = _screen(100)
    assert "resolving and downloading" in bar_lines(rows)[0]


def test_the_label_is_dropped_rather_than_squeezed_when_narrow() -> None:
    """A split pane gets a bar it can read, not a bar and four letters."""
    _, rows = _screen(40)
    bar = bar_lines(rows)[0]
    assert "resolving" not in bar, bar
    assert "%" in bar


def test_a_warning_drawn_during_the_bar_survives_on_its_own_line() -> None:
    """The bar owns the last line and is redrawn constantly. A warning printed
    without retiring it first is overwritten by the next frame — delivered to
    nobody."""
    _, rows = _screen(100)
    warned = [r for r in rows if "a warning drawn while the bar was on screen" in r]
    assert len(warned) == 1, rows
    assert "%" not in warned[0], f"the warning shares a line with the bar: {warned[0]!r}"


def test_the_wordmark_is_drawn_above_the_bar() -> None:
    _, rows = _screen(100)
    art = [i for i, r in enumerate(rows) if "█" in r and "%" not in r]
    assert len(art) == 6, f"expected six wordmark rows, got {len(art)}"
    assert max(art) < rows.index(bar_lines(rows)[0])


def test_a_pipe_gets_the_transcript_and_no_bar() -> None:
    """The two media get the thing each can keep: a terminal cannot keep a
    transcript, and a log file cannot keep a bar."""
    result = _run_piped()
    assert "\r" not in result, "carriage returns in a redirected log"
    assert "[1/4] Checking prerequisites" in result
    assert "python 3.13.12" in result


def test_verbose_puts_the_transcript_back_on_a_terminal() -> None:
    """`-v` is the escape hatch for the one thing the bar costs: an install
    that HANGS leaves a percentage and no history."""
    _, rows = _screen(100, args=["-v"])
    assert not bar_lines(rows), "-v must not draw a bar"
    assert any("Checking prerequisites" in r for r in rows)


def test_ascii_is_available_to_anyone_whose_font_defeats_the_blocks() -> None:
    """Whether a terminal can RENDER U+2588 depends on its font, which no
    process can ask about. The override is the stated way out."""
    _, rows = _screen(100, env={"YEET_ASCII": "1"})
    assert not any("█" in r for r in rows), "YEET_ASCII must not emit block characters"
    assert any("####" in r for r in rows), rows


def _run_piped() -> str:
    import subprocess

    proc = subprocess.run(
        [str(INSTALLER), "--selftest"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": _path(), "HOME": str(Path.home()), "TERM": "xterm-256color"},
    )
    return proc.stdout


def _path() -> str:
    parts = [str(Path(p).parent) for p in (shutil.which("sh"), shutil.which("awk")) if p]
    return ":".join(dict.fromkeys(parts + ["/usr/bin", "/bin", "/usr/sbin"]))


#: The twelve stops of `theme.sunset()`, as install.sh emits them in truecolour.
#: Duplicated here on purpose: a test that derives the expected value the same
#: way the code does cannot catch the code getting it wrong.
SUNSET = [
    "95;104;216",
    "108;101;216",
    "121;97;216",
    "141;98;210",
    "165;103;200",
    "188;107;190",
    "208;115;176",
    "226;125;160",
    "235;139;140",
    "243;155;124",
    "249;173;125",
    "255;192;125",
]


def test_the_gradient_is_the_wordmarks_own_sunset() -> None:
    """The bar runs the same ramp left to right that the letters run top to
    bottom, in the order `theme.sunset()` produces.

    Twelve stops rather than six, and truecolour rather than the 256-colour
    cube, because the cube has no room between indigo and violet: `sunset(0.00)`
    and `sunset(0.09)` both quantise to index 62, so half the ramp collapsed on
    the way in and the result read as three flat bands instead of a sunset.
    """
    stream, _ = _screen(110, env={"COLORTERM": "truecolor"})
    frames = [f for f in stream.split("\r") if "%" in f and "█" in f]
    fullest = max(frames, key=lambda f: f.count("█"))
    ordered = list(dict.fromkeys(re.findall(r"\x1b\[38;2;([0-9;]+)m", fullest)))
    assert ordered == SUNSET, ordered


def test_the_wordmark_takes_every_other_stop_of_the_same_ramp() -> None:
    """Six rows out of twelve stops. One palette for the letters, the bar and
    assets/yeet.svg — three copies that used to be able to drift."""
    stream, _ = _screen(110, env={"COLORTERM": "truecolor"})
    rows = [ln for ln in stream.split("\n") if "█" in ln and "%" not in ln]
    used = [re.search(r"\x1b\[38;2;([0-9;]+)m", ln).group(1) for ln in rows[:6]]
    assert used == [SUNSET[i] for i in (0, 2, 4, 7, 9, 11)], used


def test_a_terminal_without_truecolor_still_gets_a_gradient() -> None:
    """`$COLORTERM` unset is not a reason to print one flat colour — the
    256-colour ramp is coarser and still reads as a fade."""
    stream, _ = _screen(110, env={"COLORTERM": ""})
    frames = [f for f in stream.split("\r") if "%" in f and "█" in f]
    fullest = max(frames, key=lambda f: f.count("█"))
    assert "38;2;" not in fullest, "truecolour emitted to a terminal that never claimed it"
    ordered = list(dict.fromkeys(re.findall(r"\x1b\[38;5;(\d+)m", fullest)))
    assert len(ordered) >= 5, f"only {len(ordered)} distinct colours: {ordered}"
