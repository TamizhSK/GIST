"""Detect the stack from marker files so we can pick an image / generate a flow.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.project import Ecosystem


def fingerprint(root: Path) -> list[Ecosystem]:
    """Multiple matches = polyglot project. Return all of them, ranked.

    Read `engines.node` from package.json and `requires-python` from
    pyproject.toml to pin `Ecosystem.version` rather than guessing a tag.
    """
    raise NotImplementedError
