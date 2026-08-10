"""THE code-frame renderer. rustc/eslint style. Must never itself crash.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from yeet.core.diagnostics import DiagnosticBag

CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1


def render_diagnostics(bag: DiagnosticBag, *, color: bool = True) -> str:
    """Clamp every index. Wrap in try/except and fall back to str(diagnostic).

    Risk #20 on the guide's list: the error reporter must never be the thing
    that errors. A bad line/col from a half-built IR node has to degrade to
    `file:line: message`, not take down the whole report.

    Disable color when NO_COLOR is set or stdout is not a TTY.
    """
    raise NotImplementedError
