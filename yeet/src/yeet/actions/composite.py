"""runs.using: composite — inline the steps. Tier 1, do this first.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
NOTE: resolves `uses:` into IR only. The EXECUTOR runs it — see plan.md 3.3.
See docs/architecture.md

`resolver.resolve` turns `uses:` into a ResolvedAction. `inline` turns that
back into the Step list the job actually runs: the composite's own `steps`,
with `INPUT_*` env from the step's `with:` merged into each one.
"""

from __future__ import annotations

from pathlib import Path

from yeet.actions.resolver import ResolvedAction, apply_inputs, composite_steps
from yeet.core.diagnostics import DiagnosticBag, Position
from yeet.core.ir import Step


def inline(
    action: ResolvedAction,
    with_: dict[str, object],
    bag: DiagnosticBag,
    *,
    file: Path | None = None,
    pos: Position | None = None,
) -> list[Step]:
    """Resolve `with:` against the action's inputs and return the runnable steps.

    Applies defaults, enforces required inputs (E314), warns on undeclared
    inputs (W319), then inlines the composite steps with the resulting
    `INPUT_*` env. The executor prepends these to the job's step list.
    """
    input_env = apply_inputs(action, with_, bag, file=file, pos=pos)
    return composite_steps(action, input_env)


__all__ = ["inline"]
