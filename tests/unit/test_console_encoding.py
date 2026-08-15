"""A legacy console is a stream whose `encoding` is cp1252. So use one.

`test_ascii_output.py` greps the SOURCE for non-ASCII characters near a print,
which catches a `✔` typed into a new line of `cli/`. It cannot catch the two
things that actually break a Windows user's run: a glyph assembled at runtime,
and the encode step itself. Only writing to a real cp1252 stream does that.

WHAT THIS PROVES AND WHERE. A `UnicodeEncodeError` comes from
`TextIOWrapper.write` against a codec, and that machinery is the same on every
platform — Python does not have a Windows-specific encoder. So a cp1252 stream
built here exercises the identical code path a Windows console takes, and these
tests are real evidence rather than a simulation.

WHAT IT CANNOT PROVE, so that nobody reads more into a green run than is there:
the Windows CONSOLE API. Modern Python writes to a real console through
`WriteConsoleW` and bypasses the codepage entirely; the codepage applies to
REDIRECTED output, and to a console under `PYTHONLEGACYWINDOWSSTDIO`. Those
need Windows, and `.github/workflows/ci.yml` has a `windows-console` job that
runs exactly this file's commands under `chcp 1252`. Whether a given console
FONT has a glyph for a character it can encode is a third question, and nothing
automated answers it.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from yeet.core.events import JOB_END, JOB_START, META, STDOUT, STEP_END, STEP_START, LogEvent
from yeet.reporting import theme
from yeet.reporting.console import RunConsole

#: The two that actually ship on Windows. cp437 is the original DOS codepage a
#: console still falls back to; cp1252 is the western-European ANSI one.
LEGACY_ENCODINGS = ["cp1252", "cp437"]

ROOT = Path(__file__).resolve().parents[2]


def _legacy_stream(encoding: str) -> io.TextIOWrapper:
    """A stream that RAISES on anything it cannot represent.

    `errors="strict"` is the whole point: the default for a Windows console is
    `replace`, which would turn this test green by silently printing `?` where
    the box characters were, which is the bug wearing a disguise.
    """
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict", newline="")


# --- the glyphs -------------------------------------------------------------


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_the_panel_falls_back_for_a_stream_that_cannot_take_it(encoding):
    """`panel_glyphs` asks the STREAM, not `LANG`. This is that promise."""
    glyphs = theme.panel_glyphs(_legacy_stream(encoding))

    assert glyphs == theme._PANEL_ASCII
    for glyph in glyphs:
        glyph.encode(encoding)  # raises if the fallback is not actually safe


def test_a_utf8_stream_still_gets_the_box():
    """The fallback must not be the only branch — that would be "fixed" by
    making every terminal ugly."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    assert theme.panel_glyphs(stream) == theme._PANEL_UNICODE


def test_an_unknown_encoding_is_treated_as_hostile():
    """A stream with a name no codec knows must degrade, not raise."""

    class Weird:
        encoding = "definitely-not-a-codec"

    assert theme.panel_glyphs(Weird()) == theme._PANEL_ASCII  # type: ignore[arg-type]


# --- a whole run ------------------------------------------------------------


def _event(kind: str, job: str, step: str = "", text: str = "", status: str | None = None):
    return LogEvent(ts=0.0, job=job, step=step, stream=META, text=text, kind=kind, status=status)


def _a_full_run(console: RunConsole) -> None:
    """Every event kind, including the ones that build a line at runtime."""
    console.start()
    for job in ("build", "test (node 20)"):
        console.emit(_event(JOB_START, job))
        console.emit(_event(STEP_START, job, "checkout"))
        console.emit(_event(META, job, "checkout", "::group::setup"))
        console.emit(
            LogEvent(ts=0.0, job=job, step="checkout", stream=STDOUT, text="ok", kind=STDOUT)
        )
        console.emit(_event(META, job, "checkout", "::endgroup::"))
        console.emit(_event(STEP_END, job, "checkout", status="slayed"))
        console.emit(_event(STEP_END, job, "lint", status="flopped"))
        console.emit(_event(STEP_END, job, "docs", status="skipped (not the vibe)"))
        console.emit(_event(JOB_END, job, status="flopped"))
    console.stop()


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
@pytest.mark.parametrize("color", [True, False])
def test_a_whole_run_survives_a_legacy_stream(encoding, color):
    stream = _legacy_stream(encoding)
    console = RunConsole(out=stream, color=color)

    _a_full_run(console)
    console.render_summary("flow", "flopped", 1.5, run_id="20260101-000000-abcd", job_count=2)

    stream.flush()  # the encode happens here at the latest


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
@pytest.mark.parametrize("width", [110, 100, 72, 60, 40, 34, 20])
def test_the_summary_panel_survives_every_width(encoding, width):
    """The panel degrades by WIDTH as well as by encoding, and the narrow
    branch drops the frame entirely — a different code path, and one that also
    has to encode.

    `stream=` is the contract: the glyphs are chosen by asking the stream this
    text is going to. Passing the wrong one — which is what `RunConsole` and
    the live renderer both did, by taking the `sys.stdout` default while
    writing to `self.out` — put a box character into a cp1252 file.
    """
    stream = _legacy_stream(encoding)

    text = theme.format_summary(
        "flow", "slayed", 2.0, run_id="r1", job_count=3, panel=True, width=width, stream=stream
    )
    stream.write(text)
    stream.flush()


def test_the_panel_asks_the_stream_it_writes_to_not_stdout():
    """The bug this file found. `format_summary` defaulted to `sys.stdout`
    while both renderers write to `self.out`, so on a UTF-8 console piped into
    a cp1252 file it chose the box characters by asking the console and then
    raised writing them to the file.

    Asserted as a DIFFERENCE between two streams, because a test that only
    checked the legacy one would pass just as well if the panel were ASCII
    everywhere — which would be "fixed" by making every terminal ugly.
    """
    legacy = _legacy_stream("cp1252")
    modern = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    args = ("flow", "slayed", 2.0)
    kwargs = {"run_id": "r1", "job_count": 3, "panel": True, "width": 72}

    ascii_panel = theme.format_summary(*args, **kwargs, stream=legacy)
    box_panel = theme.format_summary(*args, **kwargs, stream=modern)

    assert ascii_panel.isascii()
    assert not box_panel.isascii(), "a capable terminal must still get the box"


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_the_status_vocabulary_encodes(encoding):
    """slayed / flopped / mid / cooked / skipped, and every shared glyph."""
    for name in dir(theme):
        if name.startswith(("SYMBOL_", "STATUS_", "PANEL_", "BRANCH", "LAST_BRANCH", "PIPE")):
            value = getattr(theme, name)
            if isinstance(value, str):
                value.encode(encoding)


# --- the CLI, end to end ----------------------------------------------------


def _run_cli(*args: str, encoding: str) -> subprocess.CompletedProcess[bytes]:
    """The real command, with its stdout PIPED and the codec forced.

    A pipe rather than a terminal on purpose: redirected output is where a
    codepage still applies on Windows, and `yeet run > out.txt` is the case
    that broke. `:strict` because the default error handler would paper over
    exactly what is being tested.
    """
    return subprocess.run(
        [sys.executable, "-m", "yeet", *args],
        capture_output=True,
        cwd=ROOT,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "PYTHONIOENCODING": f"{encoding}:strict",
            # Force Python OFF its UTF-8 default so the codec above is really
            # the one used. Without this, PEP 540 mode can quietly win.
            "PYTHONUTF8": "0",
            "PYTHONPATH": str(ROOT / "src"),
            "NO_COLOR": "1",
            "TERM": "dumb",
        },
    )


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
@pytest.mark.parametrize(
    "args",
    [
        ("--help",),
        ("explain", "YEET-W402"),
        ("check", "sample_project"),
        ("scan", "sample_project"),
        # The error path too, and deliberately: typer renders a `╭─ Error ─╮`
        # box for a bad flag, which is the most likely place for a stray
        # non-ASCII character to reach a console we did not choose.
        ("check", "--not-a-flag"),
    ],
    ids=lambda a: "-".join(a).replace("--", ""),
)
def test_the_cli_writes_nothing_it_cannot_encode(encoding, args):
    done = _run_cli(*args, encoding=encoding)
    combined = done.stdout + done.stderr

    assert b"UnicodeEncodeError" not in combined, combined.decode("ascii", "replace")
    assert b"Traceback" not in combined, combined.decode("ascii", "replace")


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_the_explain_output_is_actually_readable_not_just_unraised(encoding):
    """A command that encoded fine but printed nothing would pass every
    assertion above."""
    done = _run_cli("explain", "YEET-W402", encoding=encoding)

    assert done.returncode == 0, done.stderr
    assert b"W402" in done.stdout
