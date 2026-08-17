"""The wordmark exists twice — as SVG and as ANSI — and must not drift.

`tools/gen_logo.py` draws it into `assets/yeet.svg` for the README;
`install.sh` prints the same letters with `printf` while installing. They are
duplicated because a POSIX sh script cannot import a Python module, and
duplication without a check is how two copies of a logo end up subtly
different — which is exactly the kind of thing nobody notices until someone
puts a screenshot of one next to the other.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import gen_logo  # noqa: E402

#: A wordmark row: long, and made of nothing but the block, the hash and space.
_ART_ROW = re.compile(r"'([ █#]{40,})'")


def _wordmarks(filename: str, lead: str = "") -> tuple[list[str], list[str]]:
    """The two six-row forms in an installer: (block, ascii).

    Both scripts carry the wordmark twice — `█` for a UTF-8 terminal and `#`
    for everything else — because the ASCII form is not a rarity. `LANG` unset
    is a routine macOS configuration, and Windows PowerShell 5.1 runs on
    codepage 437, so the `#` rows are what a great many people actually see.
    """
    script = (ROOT / filename).read_text(encoding="utf-8")
    rows = [row[len(lead) :] if lead else row for row in _ART_ROW.findall(script)]
    assert len(rows) == 12, f"{filename}: expected two six-row wordmarks, found {len(rows)}"
    return rows[:6], rows[6:]


def test_the_svg_and_the_installer_draw_the_same_letters() -> None:
    block, _ = _wordmarks("install.sh")
    assert block == gen_logo.ART


def test_the_powershell_installer_draws_them_too() -> None:
    """install.ps1 had no such check at all, and a wordmark nobody compares is
    a wordmark that drifts."""
    block, _ = _wordmarks("install.ps1", lead="  ")
    assert block == gen_logo.ART


def test_the_ascii_form_is_the_same_letters_in_a_different_alphabet() -> None:
    """Two spellings of one wordmark, so they are checked against each other
    rather than hand-counted twice. The `#` rows are what a stock Windows
    console and a locale-less shell get, which makes them the ones most likely
    to be edited last and least likely to be looked at."""
    for filename, lead in (("install.sh", ""), ("install.ps1", "  ")):
        block, ascii_form = _wordmarks(filename, lead)
        expected = [row.replace("█", "#") for row in block]
        assert ascii_form == expected, filename


def test_every_row_is_the_same_width() -> None:
    """A ragged row is a letter out of alignment, and it is invisible in a
    diff — the E and the T were a column apart for one commit exactly because
    the rows were hand-counted."""
    assert len({len(row) for row in gen_logo.ART}) == 1


def test_the_generated_svg_matches_the_committed_one() -> None:
    """`make check` should fail if someone edits the art and forgets to run
    the generator, for the same reason `docs/rules.md` is checked."""
    committed = (ROOT / "assets" / "yeet.svg").read_text(encoding="utf-8")
    assert gen_logo.render() == committed, "run `python tools/gen_logo.py` and commit the result"


def test_the_svg_has_no_backdrop_so_it_suits_either_github_theme() -> None:
    svg = (ROOT / "assets" / "yeet.svg").read_text(encoding="utf-8")
    head = svg.split("<g", 1)[0]
    assert "<rect" not in head, "a full-bleed backdrop rect would ship a dark slab into light mode"
