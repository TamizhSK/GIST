"""Build the DAG, detect cycles (report the cycle path), topo-sort into waves.

The algorithms live in `core.graph` so Layer 3 can reuse them without importing
upward into the planner. This module is the Job-shaped adapter over them.

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""

from __future__ import annotations

from yeet.core import graph as _graph
from yeet.core.ir import Job


def to_deps(jobs: dict[str, Job]) -> dict[str, list[str]]:
    """Job map -> plain adjacency, the form core.graph works on."""
    return {key: list(job.needs) for key, job in jobs.items()}


def topo_waves(jobs: dict[str, Job]) -> list[list[str]]:
    return _graph.topo_waves(to_deps(jobs))


def find_cycle(jobs: dict[str, Job]) -> list[str] | None:
    """Return the cycle as a path so E302 can print build -> test -> build."""
    return _graph.find_cycle(to_deps(jobs))
