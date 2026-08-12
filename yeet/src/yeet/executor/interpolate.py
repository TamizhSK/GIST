"""The `${{ }}` seam: the one place that knows how expressions are delimited.

WHY THIS FILE EXISTS (it is not in plan.md's file list). The executor has to
substitute `${{ }}` in `run:` text and decide step-level `if:`. Keeping that in
one small module means there is exactly one place that knows the delimiters,
and it is not smeared across two backends.

The evaluation itself is Dev B's (`expressions.parser` / `expressions.evaluator`)
and has landed, so the `except NotImplementedError` branches that used to guard
the seam are gone.

What remains is the `Degradation` counter, and it still guards a real case:
`RunOptions.contexts` is optional, so a caller (every executor unit test, for
one) can drive a run with no contexts at all. Then there is nothing to resolve
against and `${{ ... }}` passes through literally — which the run says once, out
loud. A workflow quietly running with a literal `${{ github.sha }}` in it is the
kind of thing you discover in a demo.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import re

from yeet.expressions.contexts import Contexts
from yeet.expressions.evaluator import evaluate
from yeet.expressions.evaluator import truthy as evaluate_truthy
from yeet.expressions.parser import parse

EXPR = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)

DEGRADED_NOTE = (
    "no expression contexts were supplied for this run — `${{ ... }}` was passed through literally"
)


class Degradation:
    """Records that we could not evaluate, so the runner can say so once.

    Once per run, not once per step: a workflow with forty expressions would
    otherwise bury its own output under the same warning forty times.
    """

    __slots__ = ("hit",)

    def __init__(self) -> None:
        self.hit = False

    def note(self) -> None:
        self.hit = True


def expand(text: str | None, ctx: Contexts | None, degraded: Degradation) -> str:
    """Substitute every `${{ ... }}` in `text`.

    An expression that fails to parse is left as written rather than replaced
    with an error string: E309 is Layer 3's job and it has already run by the
    time we are here, so the useful behaviour at execution time is to be
    transparent about what we could not resolve.
    """
    if not text:
        return text or ""
    if ctx is None:
        if EXPR.search(text):
            degraded.note()
        return text

    def replace(match: re.Match[str]) -> str:
        try:
            return _stringify(evaluate(parse(match.group("body")), ctx))
        except Exception:  # noqa: BLE001 - ExprSyntaxError et al; never kill a run
            return match.group(0)

    return EXPR.sub(replace, text)


def truthy(expr: str | None, ctx: Contexts | None, degraded: Degradation) -> bool:
    """Evaluate a step-level `if:`. Absent means "run it".

    GitHub allows `if:` with or without the braces, so strip them if present
    and hand the bare expression to the parser either way.

    When we cannot evaluate, the answer is True. Skipping a step because our
    expression engine is incomplete would silently shrink the user's build;
    running it produces a visible failure instead of an invisible omission.
    """
    if expr is None or not expr.strip():
        return True
    body = expr.strip()
    match = EXPR.fullmatch(body)
    if match:
        body = match.group("body")
    if ctx is None:
        degraded.note()
        return True
    try:
        return evaluate_truthy(evaluate(parse(body), ctx))
    except Exception:  # noqa: BLE001 - a bad `if:` is E309's problem, not a crash
        return True


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)
