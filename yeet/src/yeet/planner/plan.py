"""Workflow -> ExecutionPlan (waves of concrete job instances).

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from yeet.core.ir import Job, Workflow
from yeet.expressions.contexts import Contexts


@dataclass(frozen=True)
class JobInstance:
    """One concrete job: a Job plus the matrix leg it was expanded for.

    `key` is what `needs:` and the log tree refer to — `build` for an unmatrixed
    job, `build (node 20)` for a leg. It must be stable across runs.
    """

    job: Job
    leg: dict[str, Any] = field(default_factory=dict)
    key: str = ""


@dataclass
class ExecutionPlan:
    """Jobs inside a wave run in parallel; waves run in sequence."""

    waves: list[list[JobInstance]] = field(default_factory=list)

    @property
    def total_jobs(self) -> int:
        return sum(len(w) for w in self.waves)


def build_plan(wf: Workflow, ctx: Contexts) -> ExecutionPlan:
    """Matrix expansion FIRST, then the DAG, then topo sort into waves.

    That order matters: `needs:` targets a job name, but fail-fast and
    max-parallel apply per leg, so the graph has to be built over expanded
    instances rather than over the raw job map.
    """
    raise NotImplementedError
