"""Executor-test fixtures. Dev C's; the root conftest.py stays Dev D's.

Building IR by hand rather than parsing YAML is deliberate: `core/ir.py` and
`planner/plan.py`'s dataclasses are real and frozen, so the executor can be
tested to completion before the parser or the planner exist. That independence
is the whole reason the tier rule was worth enforcing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.core.diagnostics import Position
from yeet.core.ir import Job, Step, Strategy, Workflow
from yeet.planner.plan import ExecutionPlan, JobInstance

POS = Position(line=0, col=0)


def make_step(run: str | None = None, **kwargs: object) -> Step:
    return Step(pos=POS, run=run, **kwargs)  # type: ignore[arg-type]


def make_job(key: str = "build", steps: list[Step] | None = None, **kwargs: object) -> Job:
    return Job(key=key, pos=POS, steps=steps or [], **kwargs)  # type: ignore[arg-type]


def make_workflow(jobs: dict[str, Job], name: str = "test flow") -> Workflow:
    return Workflow(source=Path("flow.yml"), pos=POS, name=name, jobs=jobs)


def make_instance(job: Job, key: str | None = None, leg: dict[str, object] | None = None):
    return JobInstance(job=job, leg=leg or {}, key=key or job.key)


def make_plan(*waves: list[JobInstance]) -> ExecutionPlan:
    return ExecutionPlan(waves=list(waves))


def make_matrix(**values: list[object]) -> Strategy:
    return Strategy(pos=POS, matrix=dict(values))


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A directory shaped like a project: it has a `.yeet/` and is writable."""
    (tmp_path / ".yeet").mkdir()
    return tmp_path


@pytest.fixture
def docker_client():
    """A live Docker client, or skip. Pairs with `@pytest.mark.docker`.

    The marker keeps these out of `make test`; this fixture is what makes the
    skip legible when someone runs the whole suite with the daemon stopped.
    """
    from yeet.executor.backend import DockerUnavailable, get_docker_client

    try:
        return get_docker_client()
    except DockerUnavailable as exc:
        pytest.skip(f"no Docker daemon: {exc.detail}")
