"""Cross-reference checks over the IR: needs, cycles, matrix, expressions.

Scope: E301 (unknown `needs:`), E302 (dependency cycle), E303 (invalid
matrix), E304 (duplicate step id), E305 (invalid env var name), E306 (invalid
container image), E308 (invalid `uses:` reference), E309 (expression fails to
parse), E310 (unknown context), E311 (unknown function), E312 (expression in a
position that forbids one), E316 (unusable `runs-on:`), W318 (unused output).

Not here, on purpose:

* **E307 (missing secret)** — this layer cannot see which secrets exist. The
  store is tier 5 and validation is tier 3, so importing it is exactly what
  lint-imports forbids. `check_secrets(wf, available)` below is a pure function
  over a set of names; `cli/cmd_run` owns the store and calls it. Putting the
  rule here and the data there is what keeps the tier rule honest.
* **E313/E314/W319** — resolution, not shape. `actions/resolver.py` owns them:
  whether `owner/repo@ref` EXISTS is a different question from whether it is
  spelled like a reference, which is E308 below.
* **E315** — needs the image table and the project, so it fires in
  `executor/images.py` at run time. Documented in that file.
* **W317** — deprecated `::set-output::` and friends; implemented below.

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
    "env": ("env",),
    "id": ("id",),
    "uses": ("uses",),
    "container": ("container",),
    "runs-on": ("runs-on",),
    "outputs": ("outputs",),
}

#: Env names that cannot work ANYWHERE — empty, or carrying whitespace or `=`.
#:
#: Deliberately not the POSIX shell-identifier rule `[A-Za-z_][A-Za-z0-9_]*`.
#: That was the first version and the real-world corpus refuted it in one run:
#: `env: {cache-name: ...}` read back as `${{ env.cache-name }}` is the pattern
#: in GitHub's OWN caching documentation, and it appears 14 times in curl's
#: workflow. The `env` context is a map lookup, not a shell export, so a dash
#: is fine there; `=` and whitespace break the `NAME=value` shape that every
#: consumer of an environment ultimately needs.
_BAD_ENV_CHARS = frozenset("= \t\r\n\v\f\0")

#: A docker reference: [registry[:port]/]name[/name...][:tag][@digest]. Repo
#: names are lowercase — Docker rejects `Ubuntu:22.04` at the daemon, which is
#: a confusing place to find out.
IMAGE_REF = re.compile(
    r"^(?:(?P<registry>[A-Za-z0-9][A-Za-z0-9.\-]*(?::\d+)?)/)?"
    r"(?P<name>[a-z0-9]+(?:[._\-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._\-][a-z0-9]+)*)*)"
    r"(?::(?P<tag>[A-Za-z0-9_][A-Za-z0-9._\-]*))?"
    r"(?:@(?P<digest>[A-Za-z][A-Za-z0-9]*:[0-9a-fA-F]{32,}))?$"
)

#: `owner/repo@ref` or `owner/repo/sub/path@ref`.
ACTION_REF = re.compile(r"^[\w.\-]+/[\w.\-]+(?:/[\w.\-]+)*@[\w.\-/]+$")

#: `needs.<job>.outputs.<name>` inside an expression, for W318.
NEEDS_OUTPUT = re.compile(r"needs\s*\.\s*([\w\-]+)\s*\.\s*outputs\s*\.\s*([\w\-]+)")


def check(wf: Workflow) -> DiagnosticBag:
    """Collect, don't raise — the pipeline decides what an error means."""
    bag = DiagnosticBag()
    _check_needs(wf, bag)
    _check_matrix(wf, bag)
    _check_expressions(wf, bag)
    _check_step_ids(wf, bag)
    _check_env_names(wf, bag)
    _check_container_images(wf, bag)
    _check_action_refs(wf, bag)
    _check_runs_on(wf, bag)
    _check_unused_outputs(wf, bag)
    _check_deprecated(wf, bag)
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
        if not keys and not strategy.include:
            # `include:` alone IS a matrix — each entry is a leg, no base
            # variables required. Requiring a base key here rejected three of
            # the nine real workflows in tests/corpus/ (Flask, Jinja,
            # scikit-learn), which is a third of the compatibility metric we
            # intend to quote.
            bag.add(
                _error(
                    wf,
                    job,
                    "matrix",
                    "YEET-E303",
                    f"job `{job.key}` has a strategy with an empty matrix",
                    help="matrix must define at least one variable, such as `node` or `os`, "
                    "or list its legs under `include:`",
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


# --- E304 -------------------------------------------------------------------


def _check_step_ids(wf: Workflow, bag: DiagnosticBag) -> None:
    """Two steps in one job with the same `id:`.

    Registered as "duplicate job id", which cannot happen: `Workflow.jobs` is a
    dict, and two `build:` keys in one `jobs:` mapping are caught at layer 1 by
    E102 before the IR is built. The reachable version of the same mistake is
    at step level, where it silently breaks `steps.<id>.outputs` — the second
    step's outputs overwrite the first's and a later expression reads whichever
    ran last. Retitled in codes.py rather than left registered-and-unreachable.
    """
    for job in wf.jobs.values():
        seen: dict[str, Step] = {}
        for step in job.steps:
            if not step.id:
                continue
            if step.id in seen:
                bag.add(
                    _error(
                        wf,
                        step,
                        "id",
                        "YEET-E304",
                        f"job `{job.key}` has two steps with id `{step.id}`",
                        help="Step ids must be unique within a job — "
                        "`steps.<id>.outputs` cannot name both.",
                    )
                )
            else:
                seen[step.id] = step


# --- E305 -------------------------------------------------------------------


def _check_env_names(wf: Workflow, bag: DiagnosticBag) -> None:
    """Env names that cannot survive being put in an environment, at all levels."""
    for job in wf.jobs.values():
        for name in job.env:
            if _unusable_env_name(name):
                bag.add(_bad_env(wf, job, job.key, name))
        for step in job.steps:
            for name in step.env:
                if _unusable_env_name(name):
                    bag.add(_bad_env(wf, step, job.key, name))


def _unusable_env_name(name: str) -> bool:
    return not name.strip() or bool(_BAD_ENV_CHARS & set(name))


def _bad_env(wf: Workflow, holder: Job | Step, job_key: str, name: str) -> Diagnostic:
    return _error(
        wf,
        holder,
        "env",
        "YEET-E305",
        f"`{name}` in job `{job_key}` is not a usable environment variable name",
        help="An environment name cannot be empty or contain whitespace or `=`.",
    )


# --- E306 -------------------------------------------------------------------


def _check_container_images(wf: Workflow, bag: DiagnosticBag) -> None:
    for job in wf.jobs.values():
        image = (job.container_image or "").strip()
        if not image or EXPR.search(image):
            continue
        if IMAGE_REF.match(image):
            continue
        bag.add(
            _error(
                wf,
                job,
                "container",
                "YEET-E306",
                f"job `{job.key}` has an invalid container image `{image}`",
                help="Expected `[registry/]name[:tag][@digest]`, all lowercase — "
                "for example `node:20` or `ghcr.io/org/img:1.2.3`.",
            )
        )


# --- E308 -------------------------------------------------------------------


def _check_action_refs(wf: Workflow, bag: DiagnosticBag) -> None:
    """The SHAPE of `uses:`. Whether it exists is E313, in the resolver."""
    for job in wf.jobs.values():
        for step in job.steps:
            uses = (step.uses or "").strip()
            if not uses or EXPR.search(uses):
                continue  # an expression in `uses:` is E312, already reported
            if uses.startswith(("./", "../", "docker://")):
                continue
            if ACTION_REF.match(uses):
                continue
            bag.add(
                _error(
                    wf,
                    step,
                    "uses",
                    "YEET-E308",
                    f"`uses: {uses}` in job `{job.key}` is not a valid action reference",
                    help="Expected `owner/repo@ref`, `./path/to/action`, or "
                    "`docker://image:tag`."
                    + ("" if "@" in uses else " A remote action must be pinned with `@`."),
                )
            )


# --- E316 -------------------------------------------------------------------


def _check_runs_on(wf: Workflow, bag: DiagnosticBag) -> None:
    """Only the structurally unusable cases.

    Deliberately narrow. Any string is a legal runner LABEL on GitHub —
    self-hosted runners are named by their owners — so "we do not recognise it"
    is not a validation error; that is E315 at run time, where the image table
    is, and where it can say `macos-latest is not supported` about a specific
    job rather than rejecting the whole file. What is unusable at any tier is a
    blank value or one with whitespace in it.
    """
    for job in wf.jobs.values():
        raw = job.runs_on
        if raw is None or EXPR.search(raw):
            continue
        if raw.strip() and not any(c.isspace() for c in raw.strip()):
            continue
        shown = raw.strip() or "(empty)"
        bag.add(
            _error(
                wf,
                job,
                "runs-on",
                "YEET-E316",
                f"job `{job.key}` has an unusable `runs-on:` value `{shown}`",
                help="Use a single runner label like `ubuntu-latest`, an image "
                "like `node:20`, or `local` to run on the host.",
            )
        )


# --- W318 -------------------------------------------------------------------


def _check_unused_outputs(wf: Workflow, bag: DiagnosticBag) -> None:
    """A job declares an output nothing downstream reads.

    A warning, not an error: a workflow under construction legitimately
    declares an output before the consumer exists, and a validator that refuses
    to run it would be worse than useless. But the far more common case is a
    typo on the READING side — `needs.build.outputs.sha` against
    `outputs: {SHA: ...}` — and this is the only check that can see both ends.
    """
    referenced = {(job, name) for job, name in NEEDS_OUTPUT.findall(_all_expression_text(wf))}
    for job in wf.jobs.values():
        for name in job.outputs:
            if (job.key, name) not in referenced:
                bag.add(
                    Diagnostic(
                        code="YEET-W318",
                        severity=Severity.WARNING,
                        message=f"job `{job.key}` declares output `{name}`, "
                        "which no other job reads",
                        file=wf.source,
                        pos=_pos(job, "outputs"),
                        help=f"A consumer would say "
                        f"`${{{{ needs.{job.key}.outputs.{name} }}}}` "
                        f"and list `{job.key}` in its `needs:`.",
                    )
                )


def _all_expression_text(wf: Workflow) -> str:
    """Every string in the workflow that could hold an expression, joined.

    Joined rather than walked because W318 asks "does this pair appear
    anywhere", and a regex over one string cannot miss a holder that a
    hand-written walk forgot to visit — which is how `Workflow.env` went
    unread for five sessions.
    """
    parts: list[str] = list(wf.env.values())
    for job in wf.jobs.values():
        parts.extend([job.if_ or "", *job.env.values(), *job.outputs.values()])
        for step in job.steps:
            parts.extend([step.if_ or "", step.run or "", step.uses or ""])
            parts.extend(step.env.values())
            parts.extend(str(v) for v in step.with_.values())
    return "\n".join(parts)


# --- W317 -------------------------------------------------------------------

#: `::command::` forms GitHub removed, and what replaced them. `set-output` and
#: `save-state` were disabled in 2023; `set-env` and `add-path` in 2020, for a
#: security reason (they let untrusted output rewrite the environment of every
#: later step).
DEPRECATED_COMMANDS = {
    "set-output": "write `name=value` to the file in $GITHUB_OUTPUT",
    "save-state": "write `name=value` to the file in $GITHUB_STATE",
    "set-env": "write `name=value` to the file in $GITHUB_ENV",
    "add-path": "append the directory to the file in $GITHUB_PATH",
}

_DEPRECATED_RE = re.compile(r"::(" + "|".join(DEPRECATED_COMMANDS) + r")[ :]")


def _check_deprecated(wf: Workflow, bag: DiagnosticBag) -> None:
    """W317 — workflow commands GitHub has switched off.

    A warning rather than an error, and the distinction is the point: these
    still PARSE, and on GitHub they now do nothing at all. A step that ends
    `echo "::set-output name=sha::$(git rev-parse HEAD)"` runs green on
    GitHub and silently produces no output, so the job that reads
    `steps.x.outputs.sha` gets an empty string and fails somewhere else
    entirely. Saying so at check time is most of this rule's value — it is the
    kind of thing that rots in a repo nobody has touched in two years.
    """
    for job in wf.jobs.values():
        for step in job.steps:
            for match in _DEPRECATED_RE.finditer(step.run or ""):
                name = match.group(1)
                bag.add(
                    Diagnostic(
                        code="YEET-W317",
                        severity=Severity.WARNING,
                        message=f"`::{name}::` was removed by GitHub and does nothing",
                        file=wf.source,
                        pos=_pos(step, "run"),
                        help=f"Instead, {DEPRECATED_COMMANDS[name]}.",
                        note="It still parses, so a workflow using it passes and "
                        "quietly produces no value.",
                    )
                )


# --- E307 — not called from `check`; see the module docstring ----------------


def referenced_names(wf: Workflow, context: str) -> set[str]:
    """Every name a workflow reads out of one context — `secrets` or `vars`.

    The two are separate questions with one answer shape, and keeping them
    separate is what lets `cmd_run` mask secret values and leave variables
    legible: `${{ vars.NODE_ENV }}` resolving to `production` must not turn
    every `production` in the log into `***`. The workflow itself is the only
    thing that knows which name is which, because locally both come out of the
    same `.env`.
    """
    pattern = re.compile(rf"{re.escape(context)}\s*\.\s*([\w-]+)")
    found: set[str] = set()
    for job in wf.jobs.values():
        for text, _ in _secret_bearing_text(job):
            found.update(pattern.findall(text))
    for value in wf.env.values():
        found.update(pattern.findall(value))
    return found


def check_secrets(wf: Workflow, available: set[str]) -> list[Diagnostic]:
    """E307 — `${{ secrets.X }}` where X is not in the store.

    Takes the names rather than reading them: `secrets/store.py` is tier 5 and
    this module is tier 3. The caller that owns the store (`cli/cmd_run`) is
    above both and passes them down.

    `GITHUB_TOKEN` is exempt — GitHub injects it and workflows reference it
    without ever setting it, so flagging it would fire on most real files.
    """
    referenced: dict[str, Job | Step] = {}
    for job in wf.jobs.values():
        for text, holder in _secret_bearing_text(job):
            for name in re.findall(r"secrets\s*\.\s*([\w\-]+)", text):
                referenced.setdefault(name, holder)

    out: list[Diagnostic] = []
    for name, holder in referenced.items():
        if name == "GITHUB_TOKEN" or name in available:
            continue
        known = ", ".join(sorted(available)) if available else "none are set"
        out.append(
            Diagnostic(
                code="YEET-E307",
                severity=Severity.ERROR,
                message=f"`secrets.{name}` is not set",
                file=wf.source,
                pos=holder.pos,
                help=f"Add it with `yeet secrets set {name}`, or put it in .env.",
                note=f"secrets available: {known}",
            )
        )
    return out


def _secret_bearing_text(job: Job) -> list[tuple[str, Job | Step]]:
    out: list[tuple[str, Job | Step]] = [(job.if_ or "", job)]
    out.extend((v, job) for v in job.env.values())
    for step in job.steps:
        out.extend([(step.if_ or "", step), (step.run or "", step)])
        out.extend((v, step) for v in step.env.values())
        out.extend((str(v), step) for v in step.with_.values())
    return out


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
