"""A16 — golden-file tests: tests/fixtures/valid/<n>.yml + <n>.expected.json.

The pipeline is loader -> aliases -> builder. The expected file freezes the
IR structure (no positions — those have their own tests). Regenerate with
`python tools/gen_golden.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yeet.core.diagnostics import DiagnosticBag
from yeet.parser.aliases import normalize
from yeet.parser.builder import build_workflow
from yeet.parser.loader import load_with_positions

VALID = Path(__file__).parents[1] / "fixtures" / "valid"
CASES = sorted(p.name for p in VALID.glob("*.yml") if not p.name.endswith(".expected.json"))


@pytest.mark.parametrize("case", CASES)
def test_golden(case):
    yml = VALID / case
    expected_path = VALID / case.replace(".yml", ".expected.json")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    bag = DiagnosticBag()
    data = load_with_positions(yml, bag)
    assert data is not None, [d.code for d in bag.items]
    data, used = normalize(data)
    wf = build_workflow(data, yml, bag)
    assert wf is not None
    wf.used_dialect = used
    assert not bag.items, [d.message for d in bag.items]

    actual = _workflow_to_dict(wf)
    assert actual == expected


def _step_to_dict(s):
    return {
        "name": s.name,
        "id": s.id,
        "run": s.run,
        "uses": s.uses,
        "with": s.with_,
        "env": s.env,
        "if": s.if_,
        "shell": s.shell,
        "working_directory": s.working_directory,
        "continue_on_error": s.continue_on_error,
        "timeout_minutes": s.timeout_minutes,
    }


def _strategy_to_dict(st):
    if st is None:
        return None
    return {
        "matrix": st.matrix,
        "include": st.include,
        "exclude": st.exclude,
        "fail_fast": st.fail_fast,
        "max_parallel": st.max_parallel,
    }


def _job_to_dict(j):
    return {
        "key": j.key,
        "name": j.name,
        "runs_on": j.runs_on,
        "needs": j.needs,
        "env": j.env,
        "if": j.if_,
        "strategy": _strategy_to_dict(j.strategy),
        "container_image": j.container_image,
        "dockerfile": j.dockerfile,
        "timeout_minutes": j.timeout_minutes,
        "outputs": j.outputs,
        "steps": [_step_to_dict(s) for s in j.steps],
    }


def _trigger_to_dict(t):
    return {"event": t.event, "filters": t.filters}


def _workflow_to_dict(wf):
    return {
        "name": wf.name,
        "triggers": [_trigger_to_dict(t) for t in wf.triggers],
        "jobs": {k: _job_to_dict(j) for k, j in sorted(wf.jobs.items())},
        "env": wf.env,
        "defaults": wf.defaults,
        "used_dialect": wf.used_dialect,
    }
