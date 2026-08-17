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


def _banner_rows() -> list[str]:
    """The six `printf` rows of the installer's banner, unescaped."""
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    return re.findall(r"printf '  %s(.*?)%s\\n'", script)[:6]


def test_the_svg_and_the_installer_draw_the_same_letters() -> None:
    assert _banner_rows() == gen_logo.ART


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
