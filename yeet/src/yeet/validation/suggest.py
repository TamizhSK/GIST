"""difflib did-you-mean against canonical keys AND dialect aliases.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from collections.abc import Iterable


def did_you_mean(word: str, candidates: Iterable[str]) -> str | None:
    """`bild` -> `build`. Returns None when nothing is close enough.

    Match against canonical keys *and* the dialect aliases, so a user who typed
    `the_grnd` gets `the_grind` and a user who typed `job` gets `jobs`.
    """
    raise NotImplementedError
