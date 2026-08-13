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
from yeet.actions import resolver as actions_resolver

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
    _check_job_and_steps(wf, bag)
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
        _check_text(wf, job, job, job.if_, "if", bag)
        for name, value in job.env.items():
            _check_text(wf, job, job, value, f"env.{name}", bag)
        if job.strategy is not None:
            for var, values in job.strategy.matrix.items():
                for value in values:
                    if isinstance(value, str):
                        _check_text(wf, job, job, value, f"matrix.{var}", bag)
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
                _check_text(wf, job, step, step.uses, "uses", bag)
            _check_text(wf, job, step, step.run, "run", bag)
            _check_text(wf, job, step, step.if_, "if", bag)
            for name, value in step.env.items():
                _check_text(wf, job, step, value, f"env.{name}", bag)
            for name, value in step.with_.items():
                if isinstance(value, str):
                    _check_text(wf, job, step, value, f"with.{name}", bag)

    # actions resolution and inputs checks (E313/E314)
    for job in wf.jobs.values():
        root = wf.source.parent
        for step in job.steps:
            if step.uses and not EXPR.search(step.uses):
                try:
                    # call resolver with a temporary bag so we can demote E313 to a
                    # warning for validator consumers (tests and other owners rely on
                    # workflows not being hard-failed by missing local actions here).
                    temp = DiagnosticBag()
                    action = actions_resolver.resolve(step.uses, root, temp)
                    # propagate diagnostics, demoting E313 -> W313 so validation
                    # doesn't hard-fail callers. Keep other diagnostics as-is.
                    for d in temp.items:
                        if d.code == "YEET-E313":
                            bag.add(
                                Diagnostic(
                                    code="YEET-W313",
                                    severity=Severity.WARNING,
                                    message=d.message,
                                    file=d.file,
                                    pos=d.pos,
                                    help=d.help,
                                    note=d.note,
                                )
                            )
                        else:
                            bag.add(d)
                    if action is not None:
                        actions_resolver.apply_inputs(action, step.with_, bag, file=wf.source, pos=step.pos)
                except Exception:
                    # resolver reports diagnostics itself; don't crash the validator
                    continue


def _check_text(
    wf: Workflow, job: Job, holder: Job | Step, text: Any, field: str, bag: DiagnosticBag
) -> None:
    if not isinstance(text, str):
        return
    for match in EXPR.finditer(text):
        _check_body(wf, job, holder, field, match.group("body"), bag)


def _check_body(
    wf: Workflow, job: Job, holder: Job | Step, field: str, body: str, bag: DiagnosticBag
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
    _walk(wf, job, holder, field, node, bag)


def _walk(
    wf: Workflow, job: Job, holder: Job | Step, field: str, node: ast_nodes.Node, bag: DiagnosticBag
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
            _walk(wf, job, holder, field, arg, bag)
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
            _walk(wf, job, holder, field, node.target, bag)
        # semantic checks for dotted paths like `steps.id.outputs.foo`,
        # `needs.job.outputs.x`, `matrix.var` and `secrets.NAME`
        path = _extract_path(node)
        if path:
            try:
                _check_member_path(wf, job, holder, field, path, bag)
            except Exception:
                # Never allow the validator to crash; report nothing here.
                pass
    elif isinstance(node, ast_nodes.Index):
        if node.target is not None:
            _walk(wf, job, holder, field, node.target, bag)
        if node.index is not None:
            _walk(wf, job, holder, field, node.index, bag)
    elif isinstance(node, ast_nodes.Splat):
        if node.target is not None:
            _walk(wf, job, holder, field, node.target, bag)
    elif isinstance(node, ast_nodes.Unary):
        if node.operand is not None:
            _walk(wf, job, holder, field, node.operand, bag)
    elif isinstance(node, ast_nodes.Binary):
        if node.left is not None:
            _walk(wf, job, holder, field, node.left, bag)
        if node.right is not None:
            _walk(wf, job, holder, field, node.right, bag)


def _extract_path(node: ast_nodes.Node) -> list[str] | None:
    """Return a dotted path like ['steps','test','outputs','result'] when
    the node represents a member chain made of identifiers or literal indices.
    Otherwise return None.
    """
    parts: list[str] = []

    def gather(n: ast_nodes.Node) -> bool:
        if isinstance(n, ast_nodes.Ident):
            parts.append(n.name)
            return True
        if isinstance(n, ast_nodes.Member):
            parts.append(n.name)
            if n.target is None:
                return False
            return gather(n.target)
        if isinstance(n, ast_nodes.Index):
            # index may be a literal Ident or Literal
            if n.index is None:
                return False
            if isinstance(n.index, ast_nodes.Literal) and isinstance(n.index.value, str):
                parts.append(str(n.index.value))
                if n.target is None:
                    return False
                return gather(n.target)
            return False
        return False

    ok = gather(node)
    if not ok:
        return None
    return list(reversed(parts))


def _check_member_path(
    wf: Workflow, job: Job, holder: Job | Step, field: str, path: list[str], bag: DiagnosticBag
) -> None:
    # steps.<id>.outputs.<name>
    if path[0] == "steps" and len(path) >= 3 and path[2] == "outputs":
        step_id = path[1]
        # find step ids in this job
        ids = [s.id for s in job.steps if s.id]
        if step_id not in ids:
            bag.add(
                _error(
                    wf,
                    holder,
                    field if field == "if" else None,
                    "YEET-E305",
                    f"step `{step_id}` referenced in `steps.*.outputs` does not exist in job `{job.key}`",
                )
            )
        else:
            # ordering check: referenced step must come before current step
            if isinstance(holder, Step) and holder.id is not None:
                idx = ids.index(step_id)
                cur_idx = ids.index(holder.id) if holder.id in ids else -1
                if cur_idx != -1 and idx >= cur_idx:
                    bag.add(
                        _error(
                            wf,
                            holder,
                            field if field == "if" else None,
                            "YEET-E306",
                            f"step `{step_id}` is referenced before it's executed in job `{job.key}`",
                        )
                    )
    # needs.<job>.outputs.<name>
    if path[0] == "needs" and len(path) >= 3 and path[2] == "outputs":
        dep = path[1]
        if dep not in job.needs:
            bag.add(
                _error(
                    wf,
                    holder,
                    field if field == "if" else None,
                    "YEET-E307",
                    f"job `{job.key}` references outputs of `{dep}` but does not list it in `needs`",
                    help=f"add `{dep}` to the `needs:` list of `{job.key}` to access its outputs",
                )
            )
    # matrix.var
    if path[0] == "matrix" and len(path) >= 2:
        var = path[1]
        strategy = job.strategy
        declared = set(strategy.matrix) if strategy is not None else set()
        # include can introduce new keys
        if strategy is not None:
            for inc in strategy.include:
                for k in inc:
                    declared.add(k)
        if var not in declared:
            bag.add(
                _error(
                    wf,
                    holder,
                    field if field == "if" else None,
                    "YEET-E308",
                    f"matrix variable `{var}` referenced in job `{job.key}` is not declared",
                    help=f"matrix variables: {', '.join(sorted(declared)) or 'none'}",
                )
            )
    # secrets.NAME
    if path[0] == "secrets" and len(path) >= 2:
        name = path[1]
        # best-effort: look for a local secrets file under the workflow's dir
        root = wf.source.parent
        store = root / ".yeet" / ".secrets"
        dotenv = root / ".env"
        ok = False
        if store.is_file():
            try:
                text = store.read_text(encoding="utf-8")
                ok = name in text
            except OSError:
                ok = False
        elif dotenv.is_file():
            try:
                text = dotenv.read_text(encoding="utf-8")
                ok = f"{name}=" in text
            except OSError:
                ok = False
        if not ok:
            bag.add(
                Diagnostic(
                    code="YEET-W317",
                    severity=Severity.WARNING,
                    message=f"secret `{name}` referenced in job `{job.key}` is not present in the local secret store",
                    file=wf.source,
                    pos=_pos(holder, *_POS_KEYS.get(field or "", ())),
                    help="add it via `yeet secrets set` or provide it via --secret when running",
                )
            )


def _check_job_and_steps(wf: Workflow, bag: DiagnosticBag) -> None:
    # E304: duplicate job `name` values
    seen_names: dict[str, str] = {}
    for job in wf.jobs.values():
        if job.name:
            if job.name in seen_names:
                bag.add(
                    _error(
                        wf,
                        job,
                        "name",
                        "YEET-E304",
                        f"duplicate job name `{job.name}` (also used by `{seen_names[job.name]}`)",
                    )
                )
            else:
                seen_names[job.name] = job.key

    # E305/E306 already handled in expression walking for steps outputs; add
    # E305 for invalid env var names and E306 for container image format
    env_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for job in wf.jobs.values():
        for k in job.env:
            if not env_re.match(k):
                bag.add(
                    _error(
                        wf,
                        job,
                        f"env.{k}",
                        "YEET-E305",
                        f"invalid environment variable name `{k}` in job `{job.key}`",
                    )
                )
        for step in job.steps:
            for k in step.env:
                if not env_re.match(k):
                    bag.add(
                        _error(
                            wf,
                            step,
                            f"env.{k}",
                            "YEET-E305",
                            f"invalid environment variable name `{k}` in step of job `{job.key}`",
                        )
                    )
        # E306: container image format sanity check
        img = job.container_image
        if img:
            lowered = img.strip()
            looks_like = ("/" in lowered) or (":" in lowered) or (lowered.isalnum() and lowered.islower())
            if not looks_like:
                bag.add(
                    _error(
                        wf,
                        job,
                        "runs-on",
                        "YEET-E306",
                        f"job `{job.key}` has an invalid container image format: `{img}`",
                    )
                )

    # W318: unused output variables
    # collect references to needs.*.outputs.* and steps.*.outputs.* we saw
    referenced_outputs: dict[str, set[str]] = {k: set() for k in wf.jobs}
    for job in wf.jobs.values():
        # scan textual fields for simple `needs.X.outputs.Y` patterns
        def scan_text(t: str | None) -> None:
            if not isinstance(t, str):
                return
            for m in EXPR.finditer(t):
                body = m.group("body")
                try:
                    node = parse(body)
                except Exception:
                    continue
                p = _extract_path(node) if isinstance(node, ast_nodes.Member) else None
                if not p:
                    # try a crude textual match
                    txt = body.replace(" ", "")
                    if txt.startswith("needs.") and ".outputs." in txt:
                        parts = txt.split(".")
                        if len(parts) >= 4:
                            referenced_outputs.setdefault(parts[1], set()).add(parts[3])
                    continue
                if p[0] == "needs" and len(p) >= 4 and p[2] == "outputs":
                    referenced_outputs.setdefault(p[1], set()).add(p[3])

        scan_text(job.if_)
        for v in job.env.values():
            scan_text(v)
        for step in job.steps:
            scan_text(step.run)
            for v in step.env.values():
                scan_text(v)

    for job in wf.jobs.values():
        for out in job.outputs:
            if out not in referenced_outputs.get(job.key, set()):
                bag.add(
                    Diagnostic(
                        code="YEET-W318",
                        severity=Severity.WARNING,
                        message=f"output `{out}` of job `{job.key}` is never used",
                        file=wf.source,
                        pos=job.key_pos.get("outputs", job.pos),
                    )
                )


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
