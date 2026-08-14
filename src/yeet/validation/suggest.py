"""difflib did-you-mean against canonical keys AND dialect aliases.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable

_CUTOFF = 0.6


def did_you_mean(word: str, candidates: Iterable[str]) -> str | None:
    """`bild` -> `build`. Returns None when nothing is close enough.

    Match against canonical keys *and* the dialect aliases, so a user who typed
    `the_grnd` gets `the_grind` and a user who typed `job` gets `jobs`.

    The caller passes the candidate list — canonical keys, or canonical keys
    plus aliases — because only the caller knows which keys are legal *here*.
    """
    if not word:
        return None
    matches = difflib.get_close_matches(word, list(candidates), n=1, cutoff=_CUTOFF)
    return matches[0] if matches else None
