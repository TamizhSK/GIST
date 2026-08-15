"""Everything the CLI prints must survive a legacy console.

A `✔` or a `📦` is one `UnicodeEncodeError` away from taking down the command
that was only trying to tell you something: a cp437 Windows console, an ssh
session with no locale, a CI log viewer, `yeet run > out.txt` opened in an
editor that guessed latin-1. And on the consoles that CAN print them they are
usually the wrong width, which breaks every aligned column after.

`reporting.live` and the `--tui` dashboard are exempt: both have already
established that they are talking to a real terminal. `reporting.theme`'s panel
glyphs are exempt because they are chosen by asking the stream what it can
encode. Nothing in `cli/` gets to assume.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[2] / "src" / "yeet" / "cli"

#: A line that writes to the user. `typer.style` is included because its result
#: is always handed to one of the others.
PRINTS = re.compile(r"(typer\.(echo|secho|style)|_echo)\(")


def _offending_lines(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not PRINTS.search(line):
            continue
        exotic = "".join(dict.fromkeys(char for char in line if ord(char) > 127))
        if exotic:
            out.append((number, exotic))
    return out


@pytest.mark.parametrize("path", sorted(CLI.rglob("*.py")), ids=lambda p: p.name)
def test_cli_output_is_seven_bit_ascii(path: Path) -> None:
    offenders = _offending_lines(path)
    assert not offenders, "\n".join(
        f"{path.name}:{number} prints {chars!r}" for number, chars in offenders
    )


def test_the_theme_glyphs_are_ascii() -> None:
    """The shared set every command draws from."""
    from yeet.reporting import theme

    for name in (
        "SYMBOL_PASS",
        "SYMBOL_FAIL",
        "SYMBOL_SKIP",
        "SYMBOL_RUNNING",
        "SYMBOL_BULLET",
        "SYMBOL_WARN",
        "SYMBOL_NOTE",
        "SYMBOL_ARROW",
        "SYMBOL_FROM",
        "BRANCH",
        "LAST_BRANCH",
        "PIPE",
    ):
        value = getattr(theme, name)
        assert value.isascii(), f"theme.{name} = {value!r} is not ASCII"


def test_a_run_summary_encodes_on_a_legacy_console() -> None:
    """The end-to-end version: the closing line has to survive cp437."""
    from yeet.reporting.theme import ColorLevel, format_summary

    line = format_summary("ci", "slayed", 1.0, run_id="r", job_count=1, level=ColorLevel.NONE)
    line.encode("cp437")
