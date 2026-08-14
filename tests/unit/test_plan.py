"""B11: Workflow -> ExecutionPlan (waves of concrete job instances).

Matrix expansion first, then the instance DAG, then topological waves.
`needs:` names jobs; an instance of job A depends on every instance of every
job A needs, so a matrixed dependency fans out across its legs.

Owner: Dev B
"""

from __future__ import annotations

import pytest
from conftest import POS, make_job, make_workflow

from yeet.core.ir import Job, Strategy
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import ExecutionPlan, build_plan


def plan(*jobs: Job) -> ExecutionPlan:
    return build_plan(make_workflow({job.key: job for job in jobs}), Contexts())


def wave_keys(plan: ExecutionPlan) -> list[list[str]]:
    return [[inst.key for inst in wave] for wave in plan.waves]


def test_single_job_is_one_wave_of_its_own_key() -> None:
    result = plan(make_job("build"))
    assert wave_keys(result) == [["build"]]
    assert result.total_jobs == 1
    assert result.waves[0][0].job.key == "build"


def test_unmatrixed_instance_has_empty_leg() -> None:
    inst = plan(make_job("build")).waves[0][0]
    assert inst.key == "build"
    assert inst.leg == {}


def test_matrix_legs_become_suffixed_instances() -> None:
    job = make_job(
        "build",
        strategy=Strategy(pos=POS, matrix={"node": [18, 20], "os": ["ubuntu", "windows"]}),
    )
    assert wave_keys(plan(job)) == [
        [
            "build (node 18, os ubuntu)",
            "build (node 18, os windows)",
            "build (node 20, os ubuntu)",
            "build (node 20, os windows)",
        ]
    ]


def test_matrix_leg_values_are_preserved_on_instances() -> None:
    job = make_job("build", strategy=Strategy(pos=POS, matrix={"node": [18, 20]}))
    legs = [inst.leg for inst in plan(job).waves[0]]
    assert legs == [{"node": 18}, {"node": 20}]


def test_needs_splits_jobs_into_sequential_waves() -> None:
    result = plan(make_job("build"), make_job("deploy", needs=["build"]))
    assert wave_keys(result) == [["build"], ["deploy"]]


def test_diamond_dependency_layers_correctly() -> None:
    result = plan(
        make_job("a"),
        make_job("b", needs=["a"]),
        make_job("c", needs=["a"]),
        make_job("d", needs=["b", "c"]),
    )
    assert wave_keys(result) == [["a"], ["b", "c"], ["d"]]


def test_matrixed_job_fans_out_into_dependency_legs() -> None:
    build = make_job("build", strategy=Strategy(pos=POS, matrix={"node": [18, 20]}))
    deploy = make_job("deploy", needs=["build"])
    result = plan(build, deploy)
    assert wave_keys(result) == [
        ["build (node 18)", "build (node 20)"],
        ["deploy"],
    ]
    (deploy_inst,) = result.waves[1]
    assert deploy_inst.job.needs == ["build"]


def test_unknown_needs_do_not_crash_the_planner() -> None:
    result = plan(make_job("deploy", needs=["ghost"]))
    assert wave_keys(result) == [["deploy"]]


def test_cycle_raises_with_path() -> None:
    with pytest.raises(ValueError, match="dependency cycle"):
        plan(make_job("a", needs=["b"]), make_job("b", needs=["a"]))


def test_self_need_raises() -> None:
    with pytest.raises(ValueError, match="dependency cycle"):
        plan(make_job("a", needs=["a"]))


def test_empty_workflow_yields_empty_plan() -> None:
    result = build_plan(make_workflow({}), Contexts())
    assert result.waves == []
    assert result.total_jobs == 0


def test_leg_keys_are_stable_across_rebuilds() -> None:
    job = make_job("build", strategy=Strategy(pos=POS, matrix={"node": [18, 20]}))
    first = wave_keys(plan(job))
    second = wave_keys(plan(job))
    assert first == second


def test_include_and_exclude_shape_the_instance_set() -> None:
    job = make_job(
        "build",
        strategy=Strategy(
            pos=POS,
            matrix={"os": ["ubuntu", "windows"]},
            include=[{"os": "ubuntu", "version": 18}],
            exclude=[{"os": "windows"}],
        ),
    )
    assert wave_keys(plan(job)) == [["build (os ubuntu, version 18)"]]
