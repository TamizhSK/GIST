"""Generate golden expected.json files for tests/fixtures/valid/*.yml.

Run from repo root: python tools/gen_golden.py
Freezes the IR produced by loader -> aliases -> builder, minus positions (the
renderer tests those separately) so the golden files are about structure.
"""

from __future__ import annotations

import json
from pathlib import Path

from yeet.core.ir import Job, Step, Strategy, Trigger, Workflow
from yeet.core.diagnostics import DiagnosticBag
from yeet.parser.loader import load_with_positions
from yeet.parser.aliases import normalize
from yeet.parser.builder import build_workflow

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "valid"


def step_to_dict(s: Step) -> dict:
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


def strategy_to_dict(st: Strategy | None) -> dict | None:
    if st is None:
        return None
    return {
        "matrix": st.matrix,
        "include": st.include,
        "exclude": st.exclude,
        "fail_fast": st.fail_fast,
        "max_parallel": st.max_parallel,
    }


def job_to_dict(j: Job) -> dict:
    return {
        "key": j.key,
        "name": j.name,
        "runs_on": j.runs_on,
        "needs": j.needs,
        "env": j.env,
        "if": j.if_,
        "strategy": strategy_to_dict(j.strategy),
        "container_image": j.container_image,
        "dockerfile": j.dockerfile,
        "timeout_minutes": j.timeout_minutes,
        "outputs": j.outputs,
        "steps": [step_to_dict(s) for s in j.steps],
    }


def trigger_to_dict(t: Trigger) -> dict:
    return {"event": t.event, "filters": t.filters}


def workflow_to_dict(wf: Workflow) -> dict:
    return {
        "name": wf.name,
        "triggers": [trigger_to_dict(t) for t in wf.triggers],
        "jobs": {k: job_to_dict(j) for k, j in sorted(wf.jobs.items())},
        "env": wf.env,
        "defaults": wf.defaults,
        "used_dialect": wf.used_dialect,
    }


def main() -> None:
    for yml in sorted(FIXTURES.glob("*.yml")):
        bag = DiagnosticBag()
        data = load_with_positions(yml, bag)
        assert data is not None, f"{yml}: loader failed: {[d.code for d in bag.items]}"
        data, used = normalize(data)
        wf = build_workflow(data, yml, bag)
        assert wf is not None
        wf.used_dialect = used
        expected = workflow_to_dict(wf)
        out = yml.with_suffix(".expected.json")
        out.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out.name}")


if __name__ == "__main__":
    main()
