"""YAML syntax + duplicate keys + the `on:`-is-True trap.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import DiagnosticBag


def check(path: Path) -> tuple[DiagnosticBag, Any | None]:
    """Returns (bag, raw_tree). The tree is None when the file did not parse.

    W105: YAML 1.1 resolves unquoted `on`, `off`, `yes`, `no`, `y`, `n` to
    booleans, so `on:` arrives as the key `True`. GitHub tolerates it and so
    must we — normalize the key back to "on" and warn. Same trap turns a branch
    named `no` into `False` (the Norway problem).
    """
    raise NotImplementedError
