"""github, env, job, steps, runner, matrix, needs, secrets, inputs, vars.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""
from __future__ import annotations

def build_github_context(root: Path, event: str) -> dict[str, object]:
    raise NotImplementedError
