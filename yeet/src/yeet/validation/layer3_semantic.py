"""Cross-reference checks over the IR: needs, cycles, matrix, expressions.

Scope today: E301 (unknown `needs:`), E302 (dependency cycle), E303 (invalid
matrix), E309 (expression fails to parse), E310 (unknown context), E311
(unknown function), E312 (expression in a position that forbids one). The
remaining Layer 3 codes (E304-E308, E313-E317, W318-W319) are owned elsewhere
and land with their owners' conventions.

E302 calls `core.graph.find_cycle` — the SAME function the scheduler uses.
Do not write a second cycle walk; two copies drift and then the validator
and the planner disagree about whether a workflow is runnable.

(The guide says "planner.graph does double duty". It cannot: planner is
tier 4, validation is tier 3, and importing upward is what lint-imports
exists to stop. The algorithm therefore sits in core.graph and both sides
adapt to it. See plan.md 3.5.)

Owner: Dev B
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import re
from typing import Any

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.graph import find_cycle
from yeet.core.ir import Job, Step, Workflow
from yeet.expressions import ast_nodes
from yeet.expressions.ast_nodes import ExprSyntaxError
from yeet.expressions.functions import FUNCTIONS
from yeet.expressions.parser import parse

__all__ = ["check", "find_cycle"]

EXPR = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)

KNOWN_CONTEXTS = frozenset(
    {
        "github",
        "needs",
        "strategy",
        "matrix",
        "job",
        "runner",
        "env",
        "vars",
        "steps",
        "inputs",
        "secrets",
        "jobs",
    }
)

_POS_KEYS = {
    "needs": ("needs", "after"),
    "strategy": ("strategy", "squad"),
    "matrix": ("matrix", "multiverse"),
    "if": ("only_if", "if"),
}


def check(wf: Workflow) -> DiagnosticBag:
    """Collect, don't raise — the pipeline decides what an error means."""
    bag = DiagnosticBag()
    _check_needs(wf, bag)
    _check_matrix(wf, bag)
    _check_expressions(wf, bag)
    return bag


# --- E301 / E302 -----------------------------------------------------------


def _check_needs(wf: Workflow, bag: DiagnosticBag) -> None:
    known = set(wf.jobs)
    for job in wf.jobs.values():
        for need in job.needs:
            if need not in known:
                bag.add(
                    _error(
                        wf,
                        job,
                        "needs",
                        "YEET-E301",
                        f"job `{job.key}` needs `{need}`, but no job by that name exists",
                        note=f"known jobs: {', '.join(sorted(known))}" if known else None,
                    )
                )

    cycle = find_cycle({key: list(job.needs) for key, job in wf.jobs.items()})
    if cycle is not None:
        head = wf.jobs.get(cycle[0])
        bag.add(
            _error(
                wf,
                head if head is not None else next(iter(wf.jobs.values())),
                None,
                "YEET-E302",
                "dependency cycle: " + " -> ".join(cycle),
            )
        )


# --- E303 ------------------------------------------------------------------


def _check_matrix(wf: Workflow, bag: DiagnosticBag) -> None:
    for job in wf.jobs.values():
        strategy = job.strategy
        if strategy is None:
            continue
        keys = set(strategy.matrix)
        if not keys:
            bag.add(
                _error(
                    wf,
                    job,
                    "matrix",
                    "YEET-E303",
                    f"job `{job.key}` has a strategy with an empty matrix",
                    help="matrix must define at least one variable, such as `node` or `os`",
                )
            )
        for entry in strategy.exclude:
            for key in entry:
                if key not in keys:
                    bag.add(
                        _error(
                            wf,
                            job,
                            "matrix",
                            "YEET-E303",
                            f"job `{job.key}` excludes on `{key}`, which is not a matrix variable",
                            help=f"matrix variables: {', '.join(sorted(keys)) or 'none'}",
                        )
                    )


# --- E309 / E310 / E311 / E312 ----------------------------------------------


def _check_expressions(wf: Workflow, bag: DiagnosticBag) -> None:
    for job in wf.jobs.values():
        _check_text(wf, job, job.if_, "if", bag)
        for name, value in job.env.items():
            _check_text(wf, job, value, f"env.{name}", bag)
        if job.strategy is not None:
            for var, values in job.strategy.matrix.items():
                for value in values:
                    if isinstance(value, str):
                        _check_text(wf, job, value, f"matrix.{var}", bag)
        for step in job.steps:
            if step.uses and EXPR.search(step.uses):
                bag.add(
                    _error(
                        wf,
                        step,
                        None,
                        "YEET-E312",
                        f"`uses:` in job `{job.key}` cannot contain an expression",
                        help="GitHub requires `uses:` to be a literal action reference",
                    )
                )
            else:
                _check_text(wf, step, step.uses, "uses", bag)
            _check_text(wf, step, step.run, "run", bag)
            _check_text(wf, step, step.if_, "if", bag)
            for name, value in step.env.items():
                _check_text(wf, step, value, f"env.{name}", bag)
            for name, value in step.with_.items():
                if isinstance(value, str):
                    _check_text(wf, step, value, f"with.{name}", bag)


def _check_text(
    wf: Workflow, holder: Job | Step, text: Any, field: str, bag: DiagnosticBag
) -> None:
    if not isinstance(text, str):
        return
    for match in EXPR.finditer(text):
        _check_body(wf, holder, field, match.group("body"), bag)


def _check_body(
    wf: Workflow, holder: Job | Step, field: str, body: str, bag: DiagnosticBag
) -> None:
    try:
        node = parse(body)
    except ExprSyntaxError as exc:
        bag.add(
            _error(
                wf,
                holder,
                "if" if field == "if" else None,
                "YEET-E309",
                f"expression in `{field}` does not parse: {exc.message}",
                note=f"expression was: ${{{{ {body} }}}}",
            )
        )
        return
    _walk(wf, holder, field, node, bag)


def _walk(
    wf: Workflow, holder: Job | Step, field: str, node: ast_nodes.Node, bag: DiagnosticBag
) -> None:
    if isinstance(node, ast_nodes.Call):
        if node.name.lower() not in FUNCTIONS:
            bag.add(
                _error(
                    wf,
                    holder,
                    "if" if field == "if" else None,
                    "YEET-E311",
                    f"unknown function `{node.name}` in `{field}`",
                    note=f"at character {node.offset}",
                )
            )
        for arg in node.args:
            _walk(wf, holder, field, arg, bag)
    elif isinstance(node, ast_nodes.Ident):
        if node.name.lower() not in KNOWN_CONTEXTS:
            bag.add(
                _error(
                    wf,
                    holder,
                    "if" if field == "if" else None,
                    "YEET-E310",
                    f"unknown context `{node.name}` in `{field}`",
                    note=f"at character {node.offset}",
                )
            )
    elif isinstance(node, ast_nodes.Member):
        if node.target is not None:
            _walk(wf, holder, field, node.target, bag)
    elif isinstance(node, ast_nodes.Index):
        if node.target is not None:
            _walk(wf, holder, field, node.target, bag)
        if node.index is not None:
            _walk(wf, holder, field, node.index, bag)
    elif isinstance(node, ast_nodes.Splat):
        if node.target is not None:
            _walk(wf, holder, field, node.target, bag)
    elif isinstance(node, ast_nodes.Unary):
        if node.operand is not None:
            _walk(wf, holder, field, node.operand, bag)
    elif isinstance(node, ast_nodes.Binary):
        if node.left is not None:
            _walk(wf, holder, field, node.left, bag)
        if node.right is not None:
            _walk(wf, holder, field, node.right, bag)


# --- diagnostics ------------------------------------------------------------


def _error(
    wf: Workflow,
    holder: Job | Step,
    field: str | None,
    code: str,
    message: str,
    *,
    note: str | None = None,
    help: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=Severity.ERROR,
        message=message,
        file=wf.source,
        pos=_pos(holder, *_POS_KEYS.get(field or "", ())),
        help=help,
        note=note,
    )


def _pos(holder: Job | Step, *keys: str) -> Position:
    for key in keys:
        pos = holder.key_pos.get(key)
        if pos is not None:
            return pos
    return holder.pos or Position.unknown()
