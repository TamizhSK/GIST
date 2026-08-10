"""github, env, job, steps, runner, matrix, needs, secrets, inputs, vars.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Contexts:
    """Everything `${{ }}` can see. Passed by value into each evaluation.

    Unknown context name -> E310, so this list is also the validator's
    allow-list. Keep them in sync.
    """

    github: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    job: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, Any] = field(default_factory=dict)
    runner: dict[str, Any] = field(default_factory=dict)
    matrix: dict[str, Any] = field(default_factory=dict)
    needs: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)

    NAMES = (
        "github",
        "env",
        "job",
        "steps",
        "runner",
        "matrix",
        "needs",
        "secrets",
        "inputs",
        "vars",
    )


def build_github_context(root: Path, event: str) -> dict[str, object]:
    """sha, ref, ref_name, repository, actor, event_name, workspace, run_id,
    run_number. Must degrade gracefully when the project is not a git repo."""
    raise NotImplementedError
