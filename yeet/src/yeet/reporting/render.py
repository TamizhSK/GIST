"""THE code-frame renderer. rustc/eslint style. Must never itself crash.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""
from __future__ import annotations

CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1


def render_diagnostics(bag: "DiagnosticBag", *, color: bool = True) -> str:
    """Clamp every index. Wrap in try/except and fall back to str(diagnostic)."""
    raise NotImplementedError
