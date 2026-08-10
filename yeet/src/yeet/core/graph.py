"""Cycle detection and topological layering over a plain adjacency map.

Why this is in core and not in `planner/`: the guide says write the cycle walk
once, because the scheduler needs it and Layer 3 needs it for E302. But
`validation` is tier 3 and `planner` is tier 4 — validation importing the
planner is exactly the upward import the contract forbids. So the algorithm
lives here, at the bottom, and both callers adapt their own types to it.

Deliberately knows nothing about Job or Workflow: it takes `{node: [deps]}` and
returns names. That keeps core free of IR semantics and makes it trivial to test.

Owner: Dev B
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Deps = Mapping[str, Sequence[str]]


def find_cycle(deps: Deps) -> list[str] | None:
    """Return the cycle as a PATH, e.g. ["build", "test", "build"].

    Returning the path rather than a bool is the whole point: E302 has to print
    `build -> test -> build` or the user has to find it themselves.
    """
    raise NotImplementedError


def topo_waves(deps: Deps) -> list[list[str]]:
    """Group into waves: everything in a wave may run in parallel, waves run in
    order. Raises ValueError if the graph has a cycle — call find_cycle first.

    Unknown dependency names are the CALLER's problem to diagnose (that is
    E301); this function treats them as satisfied so that one bad `needs:`
    does not also produce a spurious cycle error.
    """
    raise NotImplementedError
