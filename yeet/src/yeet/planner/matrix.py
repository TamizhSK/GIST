"""Expand strategy.matrix -> concrete legs. include AFTER exclude order matters.

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""

from __future__ import annotations

from itertools import product
from typing import Any

from yeet.core.ir import Job


def expand(job: Job) -> list[dict[str, Any]]:
    """Cartesian product, then `exclude`, then `include`. In that order.

    That is GitHub's order and it is load-bearing. `exclude` only ever removes
    legs from the base product; `include` runs afterwards and both extends
    surviving legs and appends new ones, so an include entry that reproduces an
    excluded leg deliberately resurrects it. Running exclude last instead is
    the classic matrix bug — a leg keeps reappearing because include already
    ran.

    An include entry merges into every product leg it does not overwrite: each
    key it carries must be absent from that leg's *original* product values or
    hold an equal value. Overwrites of values added by earlier include entries
    are allowed (GitHub: `{color: pink}` overwrites the `{color: green}` a
    previous entry merged in). Entries that overwrite any original product leg
    — or match none at all — become new legs, appended in declaration order
    after the product. New legs are never merge targets: only the original
    product counts.

    A job with no strategy returns [{}] — one leg, no variables. Callers can
    then treat every job identically.
    """
    strategy = job.strategy
    if strategy is None or not strategy.matrix:
        return [{}]

    keys = list(strategy.matrix)
    product_legs = [
        dict(zip(keys, values, strict=True))
        for values in product(*(strategy.matrix[key] for key in keys))
    ]

    if strategy.exclude:
        product_legs = [
            leg
            for leg in product_legs
            if not any(
                all(key in leg and exclude[key] == leg[key] for key in exclude)
                for exclude in strategy.exclude
            )
        ]

    legs = list(product_legs)
    originals = [dict(leg) for leg in product_legs]

    if strategy.include:
        for include in strategy.include:
            merged = False
            for index, original in enumerate(originals):
                if all(
                    key not in original or original[key] == value for key, value in include.items()
                ):
                    legs[index].update(include)
                    merged = True
            if not merged:
                legs.append(dict(include))

    return legs
