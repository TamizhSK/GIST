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

    A three-colour DFS. On hitting a back edge to a node still on the stack we
    slice the stack at that node and close the loop. Unknown dependency names
    are dead ends here: a name that is not a key cannot be part of a cycle.
    """
    GREY, BLACK = 1, 2
    colour: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for dep in deps.get(node, ()):
            if dep not in deps:
                continue  # unknown name -> E301's problem, not a cycle
            if colour.get(dep, 0) == GREY:
                start = stack.index(dep)
                return stack[start:] + [dep]
            if dep not in colour:
                found = visit(dep)
                if found is not None:
                    return found
        stack.pop()
        colour[node] = BLACK
        return None

    for node in deps:
        if node not in colour:
            found = visit(node)
            if found is not None:
                return found
    return None


def topo_waves(deps: Deps) -> list[list[str]]:
    """Group into waves: everything in a wave may run in parallel, waves run in
    order. Raises ValueError if the graph has a cycle — call find_cycle first.

    Unknown dependency names are the CALLER's problem to diagnose (that is
    E301); this function treats them as satisfied so that one bad `needs:`
    does not also produce a spurious cycle error.
    """
    dependents: dict[str, list[str]] = {}
    for node, needs in deps.items():
        for needed in needs:
            if needed in deps:
                dependents.setdefault(needed, []).append(node)

    indegree = {node: sum(1 for needed in needs if needed in deps) for node, needs in deps.items()}
    ready = [node for node in deps if indegree[node] == 0]
    waves: list[list[str]] = []
    placed = 0

    while ready:
        waves.append(ready)
        placed += len(ready)
        next_ready: list[str] = []
        for node in ready:
            for dependent in dependents.get(node, ()):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    next_ready.append(dependent)
        ready = next_ready

    if placed != len(deps):
        cycle = find_cycle(deps) or ["<unknown>"]
        raise ValueError("dependency cycle: " + " -> ".join(cycle))
    return waves
