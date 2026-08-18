"""Workflow -> ExecutionPlan (waves of concrete job instances).

Owner: Dev B
Tier: 4 — may import from: core, expressions, reporting, parser, analyzer, validation
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from yeet.core import graph as _graph
from yeet.core.ir import Job, Workflow
from yeet.expressions.contexts import Contexts
from yeet.planner.matrix import expand


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
    instances rather than over the raw job map. An instance of job A depends
    on every instance of every job A needs.

    Instance keys are stable across runs: `build` for an unmatrixed job,
    `build (node 18, os ubuntu)` for a leg, in matrix declaration order. The
    runner resolves `needs:` through its job-of map, so keys only need to be
    unique here, but the log tree reads better when they match GitHub's shape.

    A dependency cycle raises ValueError with the cycle path; unknown `needs:`
    names are treated as satisfied so a bad name (E301's problem, and E301
    blocks before we run) cannot also produce a spurious cycle error.
    """
    instances: list[JobInstance] = []
    for job in wf.jobs.values():
        instances.extend(_instances(job))

    waves = _graph.topo_waves(_instance_deps(instances))
    by_key = {inst.key: inst for inst in instances}
    return ExecutionPlan(waves=[[by_key[key] for key in wave] for wave in waves])


def _instances(job: Job) -> list[JobInstance]:
    legs = expand(job)
    if len(legs) == 1 and not legs[0]:
        return [JobInstance(job=job, leg={}, key=job.key)]
    return [JobInstance(job=job, leg=leg, key=_leg_key(job, leg)) for leg in legs]


def _leg_key(job: Job, leg: dict[str, Any]) -> str:
    if not leg:
        return job.key
    rendered = ", ".join(f"{key} {value}" for key, value in leg.items())
    return f"{job.key} ({rendered})"


def _instance_deps(instances: list[JobInstance]) -> dict[str, list[str]]:
    """Instance-level adjacency: every instance of a job needs every instance
    of each job named in its `needs`."""
    key_of: dict[str, list[str]] = {}
    for inst in instances:
        key_of.setdefault(inst.job.key, []).append(inst.key)

    deps: dict[str, list[str]] = {}
    for inst in instances:
        deps[inst.key] = [dep for needed in inst.job.needs for dep in key_of.get(needed, [])]
    return deps
