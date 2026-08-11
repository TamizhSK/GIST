"""B12: `yeet graph` — render_plan is the testable seam; _flows is discovery.

Owner: Dev B
"""

from __future__ import annotations

from pathlib import Path

from conftest import POS, make_job, make_workflow

from yeet.cli.cmd_graph import _flows, render_plan
from yeet.core.ir import Strategy
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import build_plan


def test_render_plan_shows_waves_and_needs() -> None:
    wf = make_workflow(
        {
            "build": make_job("build", strategy=Strategy(pos=POS, matrix={"node": [18, 20]})),
            "deploy": make_job("deploy", needs=["build"]),
        },
        name="ship it",
    )
    plan = build_plan(wf, Contexts())
    assert render_plan(wf, plan) == (
        "flow: ship it\n"
        "3 job instance(s) in 2 wave(s)\n"
        "wave 1\n"
        "  * build (node 18)\n"
        "  * build (node 20)\n"
        "wave 2\n"
        "  * deploy   (needs: build)\n"
    )


def test_render_plan_empty() -> None:
    wf = make_workflow({}, name="empty")
    plan = build_plan(wf, Contexts())
    assert render_plan(wf, plan) == (
        "flow: empty\n0 job instance(s) in 0 wave(s)\n"
    )


def test_flows_prefers_dot_yeet_over_github(tmp_path: Path) -> None:
    (tmp_path / ".yeet" / "flows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    yeet_flow = tmp_path / ".yeet" / "flows" / "a.yml"
    github_flow = tmp_path / ".github" / "workflows" / "a.yml"
    yeet_flow.write_text("")
    github_flow.write_text("")
    assert _flows(tmp_path) == [yeet_flow]


def test_flows_sorted(tmp_path: Path) -> None:
    (tmp_path / ".yeet" / "flows").mkdir(parents=True)
    b = tmp_path / ".yeet" / "flows" / "b.yml"
    a = tmp_path / ".yeet" / "flows" / "a.yml"
    b.write_text("")
    a.write_text("")
    assert _flows(tmp_path) == [a, b]


def test_flows_root_yeet_yml_fallback(tmp_path: Path) -> None:
    (tmp_path / "yeet.yml").write_text("")
    assert _flows(tmp_path) == [tmp_path / "yeet.yml"]


def test_flows_accepts_a_file_directly(tmp_path: Path) -> None:
    flow = tmp_path / "flow.yml"
    flow.write_text("")
    assert _flows(flow) == [flow]
