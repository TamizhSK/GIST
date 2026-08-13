"""The contract between a step that says `uses:` and the code that stores files.

Owner: Dev C / Dev D (shared)
Tier: 0 — imports nothing from this package

WHY THIS FILE EXISTS. `actions/upload-artifact`, `download-artifact` and
`actions/cache` have to be implemented against `storage/`, and they have to be
invoked from the executor's step loop. The tier contract forbids exactly that
edge: `executor | storage | secrets` are SIBLINGS and may not import each other
(docs/adr/0007), because an executor that reaches into storage is one that can
no longer be tested without it.

So this follows the pattern the ADR already names for this situation — the same
one `core.events.LogSink` and `core.masking.Masker` use. The DATA lives here at
tier 0 where both sides may import it, the IMPLEMENTATION lives in
`storage/builtin.py`, and `cli/cmd_run` (tier 7, above both) passes the one to
the other. The executor calls a function it was handed and never learns where
files go.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class BuiltinContext:
    """Everything a built-in action gets. Deliberately not the step loop."""

    root: Path
    """The project root — where `.yeet/artifacts/` lives."""
    run_id: str
    """Artifacts are scoped to one run: a `download-artifact` sees what THIS
    run's earlier jobs uploaded, never a previous run's."""
    workspace: Path
    """What the step sees as its working directory, on the host side of the
    bind mount."""
    inputs: dict[str, object]
    """The step's `with:` block, already interpolated."""
    emit: Callable[[str], None]
    """One log line, inside the step's own group."""
    post: list[Callable[[], None]] = field(default_factory=list)
    """Callables the step loop runs when the JOB ends. `actions/cache` uses it:
    GitHub saves a cache at job end, and saving it at the `uses:` line would
    tar the dependency directory before the install step had filled it."""


@dataclass(frozen=True, slots=True)
class BuiltinResult:
    ok: bool
    outputs: dict[str, str] = field(default_factory=dict)
    """Becomes `steps.<id>.outputs.*` — `cache-hit` is the one workflows read."""
    message: str = ""


class BuiltinRunner(Protocol):
    """What `cli/cmd_run` hands the executor. `storage.builtin.run_builtin`."""

    def __call__(self, name: str, ctx: BuiltinContext) -> BuiltinResult: ...
