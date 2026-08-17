"""Normalized dict tree -> IR dataclasses. Attaches a Position to every node.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md

Input is the CANONICAL tree (aliases already rewritten): `on`, `jobs`, `runs-on`,
`needs`, `steps`, `run`/`uses`, `if`, `env`, `strategy`, `timeout-minutes`, ...

Positions come from `data.lc.value(key)` AS EACH NODE IS BUILT — never in a
second pass (risk #4 in plan.md). Every node that lint may want to point at is
also recorded in `key_pos`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.ir import Job, Step, Strategy, Trigger, Workflow

_STR = (str,)
_NUM = (int, float)
_BOOL = (bool,)


def _pos_of_key(mapping: Any, key: str) -> Position:
    """Position of `key` in a mapping, or the mapping's own start."""
    lc = getattr(mapping, "lc", None)
    if lc is None:
        return Position.unknown()
    try:
        line, col = lc.key(key)
        return Position(line, col)
    except (KeyError, TypeError, ValueError):
        return Position.unknown()


def _pos_of_value(mapping: Any, key: str) -> Position:
    """Position of the VALUE of `key` (what the diagnostics point at)."""
    lc = getattr(mapping, "lc", None)
    if lc is None:
        return Position.unknown()
    try:
        line, col = lc.value(key)
        return Position(line, col)
    except (KeyError, TypeError, ValueError):
        return Position.unknown()


def _pos_of_item(seq: Any, index: int) -> Position:
    lc = getattr(seq, "lc", None)
    if lc is None:
        return Position.unknown()
    try:
        line, col = lc.value(index)
        return Position(line, col)
    except (KeyError, TypeError, ValueError):
        return Position.unknown()


def _key_positions(mapping: Any, keys: list[str]) -> dict[str, Position]:
    return {k: _pos_of_key(mapping, k) for k in keys if k in mapping}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "yes", "on"):
        return True
    if value in (0, "0", "false", "False", "no", "off"):
        return False
    return default


def _build_strategy(data: Any, bag: DiagnosticBag) -> Strategy | None:
    if data is None:
        return None
    matrix_data = data.get("matrix")
    matrix: dict[str, list[Any]] = {}
    include: list[dict[str, Any]] = []
    exclude: list[dict[str, Any]] = []
    if isinstance(matrix_data, dict):
        for key, value in matrix_data.items():
            if key == "include" and isinstance(value, list):
                include = [dict(item) for item in value if isinstance(item, dict)]
            elif key == "exclude" and isinstance(value, list):
                exclude = [dict(item) for item in value if isinstance(item, dict)]
            elif isinstance(value, list):
                matrix[key] = list(value)
            else:
                matrix[key] = [value]
    return Strategy(
        pos=_pos_of_key(data, "matrix") if "matrix" in data else Position.unknown(),
        matrix=matrix,
        include=include,
        exclude=exclude,
        fail_fast=_as_bool(data.get("fail-fast", True), default=True),
        max_parallel=data.get("max-parallel"),
    )


def _build_step(data: Any, source: Path, bag: DiagnosticBag) -> Step | None:
    """Build one Step. Emits E204 (both run+uses) / E205 (neither)."""
    if not isinstance(data, dict):
        return None
    run = data.get("run")
    uses = data.get("uses")
    has_run = isinstance(run, str)
    has_uses = isinstance(uses, str)

    if has_run and has_uses:
        bag.add(
            Diagnostic(
                code="YEET-E204",
                severity=Severity.ERROR,
                message="a step can't have both `run` and `uses`",
                file=source,
                pos=_pos_of_key(data, "uses"),
                help="pick one: run a command, or use an action",
            )
        )
    elif not has_run and not has_uses:
        bag.add(
            Diagnostic(
                code="YEET-E205",
                severity=Severity.ERROR,
                message="a step needs either `run` or `uses`",
                file=source,
                pos=Position.unknown(),
                help="give it a command to run, or point it at an action",
            )
        )

    keys = [
        "name",
        "id",
        "run",
        "uses",
        "with",
        "env",
        "if",
        "shell",
        "working-directory",
        "continue-on-error",
        "timeout-minutes",
    ]
    anchor = next((k for k in keys if k in data), None)
    with_data = data.get("with")
    return Step(
        pos=_pos_of_value(data, anchor) if anchor else Position.unknown(),
        name=data.get("name"),
        id=data.get("id"),
        run=run if has_run else None,
        uses=uses if has_uses else None,
        with_=dict(with_data) if isinstance(with_data, dict) else {},
        env=_as_str_dict(data.get("env")),
        if_=data.get("if"),
        shell=data.get("shell"),
        working_directory=data.get("working-directory"),
        continue_on_error=_as_bool(data.get("continue-on-error")),
        timeout_minutes=data.get("timeout-minutes"),
        key_pos=_key_positions(data, keys),
    )


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _build_job(key: str, data: Any, jobs_map: Any, source: Path, bag: DiagnosticBag) -> Job | None:
    if not isinstance(data, dict):
        return None
    steps: list[Step] = []
    steps_data = data.get("steps")
    if isinstance(steps_data, list):
        for item in steps_data:
            step = _build_step(item, source, bag)
            if step is not None:
                steps.append(step)

    keys = [
        "name",
        "runs-on",
        "needs",
        "steps",
        "env",
        "if",
        "strategy",
        "container",
        "timeout-minutes",
        "outputs",
    ]
    needs_raw = data.get("needs")
    needs: list[str] = []
    if needs_raw is not None:
        needs = [str(n) for n in _as_list(needs_raw)]

    container = data.get("container")
    container_image: str | None = None
    dockerfile: str | None = None
    if isinstance(container, str):
        container_image = container
    elif isinstance(container, dict):
        container_image = container.get("image")
        dockerfile = container.get("dockerfile")

    return Job(
        key=key,
        pos=_pos_of_value(jobs_map, key) if jobs_map is not None else Position.unknown(),
        name=data.get("name"),
        runs_on=data.get("runs-on"),
        needs=needs,
        steps=steps,
        env=_as_str_dict(data.get("env")),
        if_=data.get("if"),
        strategy=_build_strategy(data.get("strategy"), bag),
        container_image=container_image,
        dockerfile=dockerfile,
        timeout_minutes=data.get("timeout-minutes"),
        outputs=_as_str_dict(data.get("outputs")),
        key_pos=_key_positions(data, keys),
    )


def _build_triggers(data: Any) -> list[Trigger]:
    """`on:` can be a string, a list, or a mapping of event -> filters.

    `manual` -> `workflow_dispatch` (the dialect alias, value not key).
    """
    raw = data.get("on") if isinstance(data, dict) else None
    if raw is None:
        return []

    triggers: list[Trigger] = []

    def one(event: Any, filters: Any, pos: Position) -> None:
        name = "workflow_dispatch" if event == "manual" else str(event)
        fdict = filters if isinstance(filters, dict) else {}
        triggers.append(Trigger(event=name, pos=pos, filters=fdict))

    if isinstance(raw, str):
        one(raw, {}, Position.unknown())
    elif isinstance(raw, list):
        for event in raw:
            one(event, {}, Position.unknown())
    elif isinstance(raw, dict):
        for event, filters in raw.items():
            pos = _pos_of_key(raw, event) if isinstance(event, str) else Position.unknown()
            one(event, filters, pos)
    return triggers


def build_workflow(data: Any, source: Path, bag: DiagnosticBag) -> Workflow | None:
    """Normalized dict tree -> Workflow.

    Returns None on a fatal structural failure (non-mapping root). E204/E205
    are emitted as each Step is built; everything else is collect-and-continue.
    """
    if not isinstance(data, dict):
        return None

    jobs: dict[str, Job] = {}
    jobs_data = data.get("jobs")
    if isinstance(jobs_data, dict):
        for key, job_data in jobs_data.items():
            job = _build_job(key, job_data, jobs_data, source, bag)
            if job is not None:
                jobs[key] = job

    return Workflow(
        source=source,
        pos=Position.unknown(),
        name=data.get("name"),
        triggers=_build_triggers(data),
        jobs=jobs,
        env=_as_str_dict(data.get("env")),
        defaults=_as_defaults(data.get("defaults")),
        raw=data,
    )


def _as_defaults(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
