#!/usr/bin/env python3
"""Generate assets/yeet.svg — the ASCII block-art wordmark.

Run:  python tools/gen_logo.py     (then commit assets/yeet.svg)

It stays ASCII art because this is a terminal tool and the logo should look
like something a terminal could have printed. The grid below is the source; the
SVG is one `<rect>` and one `<text>` per cell, which is the same thing an ANSI
export does with a `<span>` per cell and for the same reason.

Three decisions worth keeping:

* **Colour is sampled per ROW** from GTA VI's sunset — indigo at the top of the
  word, magenta through the middle, a low sun at the baseline — so the gradient
  runs down the letters in twelve steps rather than being applied once to the
  whole thing.

* **Each row gets two tones from that one sample.** `mid` fills the cell and
  `light` draws the glyph on top. Because `░▒▓` are partial glyphs, light-over-
  mid is what makes `▓` read as a lit edge and `▒` as a soft one: the dither
  does the blending, one hue, two values. That is the whole bevel, and it is
  why the letters are `▓`-capped and `▒`-footed rather than solid `█`
  throughout — solid blocks were legible and looked like a spreadsheet.

* **Every cell paints its rect first**, with `shape-rendering="crispEdges"` so
  the cells tile without seams, while the glyphs stay antialiased so the bevel
  stays soft. A glyph alone leaves hairlines of page colour wherever the font's
  advance and the grid disagree by a fraction of a pixel.

The top row is drawn in `deep` with no fill behind it: it is the edge above the
letters, and giving it the same treatment as the body flattened the word.

There is no backdrop rect. The mark is transparent so it sits on GitHub's light
theme and its dark one without carrying a slab of chosen background into
either, which is also why every tone is a mid-to-light value that holds against
white as well as against near-black.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "yeet.svg"
OUT_TXT = Path(__file__).resolve().parents[1] / "assets" / "yeet.txt"

# --- the art ------------------------------------------------------------------
# SHAPE and TEXTURE are separate here, and that separation is the point.
#
# The grid below says only which cells are part of a letter. Which character
# gets drawn in a cell is decided per ROW by `TEXTURE`, so the halftone runs in
# clean horizontal bands across the whole word and the letterforms stay whatever
# was drawn here. Baking the two together — which is how the previous art was
# written, `░` and `▀` typed straight into the letters — meant every attempt to
# fix a letterform also moved the shading, and every attempt to fix the shading
# broke a letter. The Y read as a 4 for exactly that reason.
#
# One block per letter, joined below, so a column cannot drift the way it can in
# four hand-counted 59-character strings.

GLYPHS: dict[str, list[str]] = {
    # THE SAME LETTERS THE INSTALLER PRINTS. `install.sh`'s banner draws this
    # art in ANSI; this draws it in SVG. They are duplicated rather than
    # generated from one source because a POSIX sh script cannot import a
    # Python module — but they must not drift, so `test_logo.py` asserts the
    # rows here and the `printf` rows there are identical, character for
    # character.
    #
    # Proportions are arithmetic, not taste. A terminal cell is about twice as
    # tall as it is wide, so row and column counts are not proportions: the
    # reference logo runs about 1.35 tall per unit wide, which at this cell
    # shape is roughly 1.4 columns per row. Six rows, thirteen columns,
    # four-cell strokes.
    "Y": [
        "████     ████",
        " ████   ████ ",
        "  ████ ████  ",
        "   ███████   ",
        "     ████    ",
        "     ████    ",
    ],
    "E": [
        "█████████",
        "████     ",
        "███████  ",
        "███████  ",
        "████     ",
        "█████████",
    ],
    "T": [
        "█████████████",
        "     ████    ",
        "     ████    ",
        "     ████    ",
        "     ████    ",
        "     ████    ",
    ],
}

WORD = "YEET"
GAP = 2  # blank columns between letters — matches the installer banner

ART = [
    (" " * GAP).join(GLYPHS[letter][row] for letter in WORD) for row in range(len(GLYPHS[WORD[0]]))
]

# The shade character for each row, top to bottom. Solid at the ends and
# thinning through the middle is what gives the strokes their rounded, tubular
# look — it is the shading the original art drew by hand, lifted out so it can
# be read (and adjusted) as the single ramp it always was.
TEXTURE = ["█", "▓", "▒", "▒", "▓", "█"]

SOLID = "█"  # a cell is part of a letter


def textured() -> list[str]:
    """ART with TEXTURE applied — the wordmark as it is actually drawn.

    THE single derivation of the dither. `render()` used to reach into
    `TEXTURE[r]` itself while `main()` printed the raw `ART` grid, so the two
    halves of the same wordmark disagreed: the SVG came out as the intended
    `█▓▒░` ramp and every plain-text copy of the logo — the terminal preview,
    anything pasted into a README — came out as solid blocks. Same art, two
    spellings, and only one of them looked like the thing we designed.
    """
    return ["".join(TEXTURE[r] if ch == SOLID else " " for ch in line) for r, line in enumerate(ART)]


# --- geometry -----------------------------------------------------------------
FONT_SIZE = 14
CELL_W = 8.4336  # the advance of Courier New at 14px, to four places
CELL_H = 16.38
PAD = 12
FONT = "'Courier New',Courier,Menlo,Monaco,monospace"

# No backdrop rect: the wordmark is transparent so it sits on GitHub's light
# theme and its dark one without carrying a black slab into either. The bevel
# notches show the PAGE through them rather than a chosen background, which is
# what a logo should do — and the reason every tone below is a mid-to-light
# value that holds its own against white as well as against near-black.

# GTA VI's sunset. Three values of one hue per stop: what fills the cell, what
# the shade characters are drawn in, and what the bevel is drawn in.
#            position   mid        light      deep
STOPS: list[tuple[float, str, str, str]] = [
    (0.00, "#3b41a8", "#5f68d8", "#2b2f80"),
    (0.22, "#5a3fae", "#7f60d8", "#432c84"),
    (0.44, "#9445a0", "#b96ac0", "#6f3079"),
    (0.62, "#c1517f", "#e07aa4", "#933a60"),
    (0.80, "#dc6f58", "#f2977c", "#a85440"),
    (1.00, "#e89a4e", "#ffc07d", "#b57334"),
]


def _mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    b = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def ramp(position: float) -> tuple[str, str, str]:
    """(mid, light, deep) at `position` down the wordmark, 0..1."""
    for i in range(len(STOPS) - 1):
        lo, *lo_tones = STOPS[i]
        hi, *hi_tones = STOPS[i + 1]
        if lo <= position <= hi:
            t = 0.0 if hi == lo else (position - lo) / (hi - lo)
            return tuple(_mix(a, b, t) for a, b in zip(lo_tones, hi_tones, strict=True))  # type: ignore[return-value]
    return tuple(STOPS[-1][1:])  # type: ignore[return-value]


def render() -> str:
    rows, cols = len(ART), max(len(line) for line in ART)
    width = round(cols * CELL_W + PAD * 2)
    height = round(rows * CELL_H + PAD * 2)

    rects: list[str] = []
    glyphs: list[str] = []

    # `textured()`, not `ART` + `TEXTURE[r]`: the shade character in the SVG and
    # the shade character in the plain-text wordmark are now one decision made
    # in one place. `light` over `mid` is what makes `░` read as a highlight
    # and `▓` as nearly solid — one hue, two values, the dither blending them.
    for r, line in enumerate(textured()):
        mid, light, _ = ramp(r / (rows - 1))
        y = PAD + r * CELL_H
        baseline = y + CELL_H - 3.4
        for c, shade in enumerate(line):
            if shade == " ":
                continue
            x = PAD + c * CELL_W
            rects.append(
                f'<rect x="{x:.3f}" y="{y:.3f}" width="{CELL_W + 0.05:.3f}" '
                f'height="{CELL_H + 0.05:.3f}" fill="{mid}"/>'
            )
            glyphs.append(f'<text x="{x:.3f}" y="{baseline:.3f}" fill="{light}">{shade}</text>')

    body = "\n  ".join(rects)
    text = "\n  ".join(glyphs)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" role="img" aria-label="yeet">
  <title>yeet — a local GitHub Actions-compatible workflow runner</title>
  <g>
  {body}
  </g>
  <g font-family="{FONT}" font-size="{FONT_SIZE}" font-weight="700">
  {text}
  </g>
</svg>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8", newline="\n")

    # The same wordmark as bytes a terminal can print. It exists so the ASCII
    # form is a generated artifact like the SVG rather than something hand-
    # retyped into a README and left to drift the next time a letter moves.
    art = textured()
    OUT_TXT.write_text("\n".join(art) + "\n", encoding="utf-8", newline="\n")

    cells = sum(1 for line in ART for ch in line if ch != " ")
    print(f"wrote {OUT.name} and {OUT_TXT.name} ({len(ART)}x{max(map(len, ART))}, {cells} cells)")
    for line in art:
        print("   " + line)


if __name__ == "__main__":
    main()
