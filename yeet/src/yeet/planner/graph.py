"""Build the DAG, detect cycles (report the cycle path), topo-sort into waves.

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""
from __future__ import annotations

def topo_waves(jobs: dict[str, "Job"]) -> list[list[str]]:
    raise NotImplementedError


def find_cycle(jobs: dict[str, "Job"]) -> list[str] | None:
    """Return the cycle as a path so E302 can print build -> test -> build."""
    raise NotImplementedError
