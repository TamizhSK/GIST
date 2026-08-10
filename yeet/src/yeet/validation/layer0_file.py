"""File & encoding: empty, non-UTF8, BOM, TAB indentation, CRLF, absurd size.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import DiagnosticBag

MAX_BYTES = 1_000_000


def check(path: Path) -> DiagnosticBag:
    """E001 E002 E003 W004 E005 W006 W007.

    Read bytes, not text — E003 has to report the offset of the bad byte, and
    you cannot do that after decoding has already thrown.

    E005 (tabs for indentation) is caught here with a regex on purpose: YAML's
    own message for it is unreadable, and it is one of the most common ways a
    hand-written workflow fails.
    """
    raise NotImplementedError
