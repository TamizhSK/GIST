"""What `@v4` means: is this ref pinned, or does it move under you?

Owner: Dev A
Tier: 0 — imports nothing from this package
See docs/architecture.md

WHY THIS FILE EXISTS. Two places need the same answer and one of them could not
reach the other. `validation/layer4_lint/pinning.py` (tier 3) has always known
which refs move — that is W402's entire job — and `actions/resolver.py` (tier 2)
now needs it too, to decide whether a cached action may be reused forever. A
tier 2 module may not import a tier 3 one, and `lint-imports` says so.

Copying the list into the resolver would have been the easy version and the
wrong one: the two answers would then be free to drift, and the drift would be
invisible — the lint would warn about `@v5` while the cache treated it as
immutable, or the reverse, and nothing would ever fail.

So the predicate moves DOWN to where both can see it. One definition, and any
new spelling of "moving" is fixed in one place for both.
"""

from __future__ import annotations

import re

MOVING_REFS = frozenset({"main", "master", "head", "latest"})
"""Branch names that are re-pointed in place, so `uses: x@main` is a different
action tomorrow than it is today."""

_MAJOR_VERSION_REF = re.compile(r"v\d+")
"""`@v4` moves too — GitHub's convention is that the major tag is re-pointed at
every minor release, which is the whole reason `actions/checkout@v4` keeps
gaining features without anyone editing a workflow."""

_SHA = re.compile(r"[0-9a-f]{40}")
"""A full commit SHA. The only ref that is immutable by construction rather
than by convention, and the one W402 asks for."""


def is_moving(ref: str) -> bool:
    """True when `ref` can point somewhere else tomorrow.

    Conservative in the direction that costs least: an unrecognised ref is
    treated as PINNED, because the alternative — re-fetching every exact tag on
    a timer — spends the network on refs that by convention never change.
    """
    text = ref.strip().lower()
    return text in MOVING_REFS or _MAJOR_VERSION_REF.fullmatch(text) is not None


def is_sha(ref: str) -> bool:
    """True for a full 40-character commit SHA, the one truly immutable ref."""
    return _SHA.fullmatch(ref.strip().lower()) is not None
