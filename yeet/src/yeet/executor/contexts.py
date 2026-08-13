"""The `${{ }}` contexts that vary per job instance and per step.

WHY THIS FILE EXISTS (it is not in plan.md's file list). `cmd_run` builds ONE
`Contexts` for the whole run and fills three of its ten fields — `github`,
`secrets`, and the process environment. Everything that varies *per job
instance* (`matrix`, `needs`, `job`) or *per step* (`env`, `steps`, `runner`)
was left at its empty default, so `${{ matrix.node }}` expanded to the empty
string in every matrix leg that has ever run, and a job's `outputs:` could not
see its own steps. The expression engine was never the problem: nothing
populated it. This module is the population.

It is a separate file rather than a few lines inside `runner.py` for one
concrete reason: **thread safety**. Jobs inside a wave run in parallel in a
`ThreadPoolExecutor`, and `Contexts` is a mutable dataclass. Mutating one
shared instance from several job threads is a race that shows up as one leg
reading another leg's matrix values — a bug that reproduces once a fortnight
and is unfalsifiable from a log. Every function here therefore *returns a new
`Contexts`* and never mutates its argument, so each instance and each step owns
its own snapshot.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from yeet.core.result import JobResult, Status
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import JobInstance

RESULT_WORDS = {
    Status.SUCCESS: "success",
    Status.FAILURE: "failure",
    Status.SKIPPED: "skipped",
    Status.CANCELLED: "cancelled",
    Status.PENDING: "skipped",
    Status.RUNNING: "success",
}
"""Status -> the word an EXPRESSION sees. Not the word the console prints.

`slayed`/`flopped` are the display vocabulary and they must not leak in here.
A real `.github/workflows/*.yml` is full of `if: needs.build.result ==
'success'`, and we promise those files run unchanged — so `needs.<job>.result`,
`job.status` and `steps.<id>.conclusion` speak GitHub's four words. The fun
vocabulary lives in `reporting/theme.py`, which is the only place it belongs.
"""

RUNNER_KEYS = {
    "os": "RUNNER_OS",
    "arch": "RUNNER_ARCH",
    "temp": "RUNNER_TEMP",
    "name": "RUNNER_NAME",
    "tool_cache": "RUNNER_TOOL_CACHE",
}
"""`runner.<key>` is read back out of the env the step will actually get.

Deriving it from `base_env` rather than from `platform_` is deliberate: the
container backend hardcodes `RUNNER_OS=Linux` regardless of the host, so a
macOS user running `cooked_on: ubuntu-latest` must see `${{ runner.os }}` ==
`Linux` — the same answer `$RUNNER_OS` gives inside that container. Asking the
host would make the expression and the variable disagree inside one step.
"""


def for_instance(
    base: Contexts | None,
    inst: JobInstance,
    upstream: dict[str, JobResult],
    job_of: dict[str, str],
) -> Contexts | None:
    """A fresh `Contexts` for one concrete job instance.

    `matrix` comes from the leg the planner expanded; `needs` from the results
    of upstream instances that have already finished; `job` reports the status
    so far. Returns None when `base` is None, because "no expression engine
    available" has to stay distinguishable from "an engine that sees nothing" —
    `interpolate` degrades visibly on the first and silently on the second.
    """
    if base is None:
        return None
    return replace(
        base,
        matrix=dict(inst.leg),
        needs=needs_context(upstream, job_of),
        job={"status": "success"},
    )


def needs_context(upstream: dict[str, JobResult], job_of: dict[str, str]) -> dict[str, Any]:
    """`needs.<job>.result` / `needs.<job>.outputs.<name>`, keyed by JOB name.

    Results arrive keyed by *instance* (`build (node 20)`) while `needs:` names
    a *job* (`build`), so the instance-to-job map does the translation rather
    than a string split — a job whose name contains a bracket would defeat the
    split, and the map is already maintained by the runner for exactly this.

    A matrix job collapses to one entry: outputs are merged across its legs and
    the result is the worst status any leg reached. That mirrors GitHub, where
    a downstream job sees a single `needs.build` no matter how many legs ran,
    and where a matrix job's outputs are last-writer-wins by construction.
    """
    merged: dict[str, Any] = {}
    for key, result in upstream.items():
        name = job_of.get(key, key)
        entry = merged.setdefault(name, {"result": "success", "outputs": {}})
        entry["outputs"].update(result.outputs)
        if not result.status.ok:
            entry["result"] = RESULT_WORDS.get(result.status, "failure")
    return merged


def for_step(
    job_ctx: Contexts | None,
    *,
    env: dict[str, str],
    base_env: dict[str, str],
    step_outputs: dict[str, dict[str, str]],
    step_conclusions: dict[str, str],
) -> Contexts | None:
    """The job's contexts, plus the three that change on every step.

    `env` is the *fully layered* environment the step is about to run with, not
    just the workflow's `env:` blocks. GitHub's `env` context is narrower, but
    the property people actually rely on locally is that `${{ env.FOO }}` and
    `$FOO` inside the same step agree; feeding the real environment in is the
    only way to guarantee that, and it can only ever expose more than GitHub
    does, never less.
    """
    if job_ctx is None:
        return None
    return replace(
        job_ctx,
        env=dict(env),
        runner=runner_context(base_env),
        steps=steps_context(step_outputs, step_conclusions),
    )


def runner_context(base_env: dict[str, str]) -> dict[str, Any]:
    """`runner.os` / `.arch` / `.temp` / `.name` / `.tool_cache` — see RUNNER_KEYS."""
    out: dict[str, Any] = {}
    for key, var in RUNNER_KEYS.items():
        value = base_env.get(var)
        if value:
            out[key] = value
    out.setdefault("name", "yeet")
    return out


def steps_context(
    step_outputs: dict[str, dict[str, str]], step_conclusions: dict[str, str]
) -> dict[str, Any]:
    """`steps.<id>.outputs.<name>`, plus `.outcome` and `.conclusion`.

    Only steps with an explicit `id:` appear, which is GitHub's rule too — an
    anonymous step has no name to reference it by.

    `outcome` and `conclusion` are the same value here. They diverge on GitHub
    only for `continue-on-error`, where `outcome` keeps the real result and
    `conclusion` reports success; that distinction belongs with whoever
    implements per-step `continue-on-error` reporting, and reporting one value
    twice is better than omitting a name that workflows commonly test.
    """
    out: dict[str, Any] = {}
    for step_id, outputs in step_outputs.items():
        conclusion = step_conclusions.get(step_id, "success")
        out[step_id] = {
            "outputs": dict(outputs),
            "outcome": conclusion,
            "conclusion": conclusion,
        }
    return out
