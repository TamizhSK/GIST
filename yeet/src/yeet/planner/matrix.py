"""Expand strategy.matrix -> concrete legs. include AFTER exclude order matters.

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""

from __future__ import annotations

from typing import Any

from yeet.core.ir import Job


def expand(job: Job) -> list[dict[str, Any]]:
    """Cartesian product, then `include`, then `exclude`. In that order.

    `include` both adds new legs and extends existing ones (an include entry
    whose keys all match an existing leg merges into it rather than creating a
    new one). `exclude` runs last and removes whole legs. Getting the order
    backwards is the classic matrix bug — an excluded leg reappearing because
    include ran after it.

    A job with no strategy returns [{}] — one leg, no variables. Callers can
    then treat every job identically.
    """
    raise NotImplementedError
