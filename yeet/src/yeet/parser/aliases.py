"""Load aliases.yml; rewrite dialect keys to canonical ones. Sets used_dialect.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ALIAS_FILE = Path(__file__).with_name("aliases.yml")


def normalize(node: Any) -> tuple[Any, bool]:
    """Recursive key rewrite. Returns (tree, used_dialect).

    Preserves ruamel position data — rewrite keys in place, do NOT rebuild the
    mappings naively or every diagnostic downstream loses its line number.

    This function never fails and never warns: it is a pure key rewrite, which
    is exactly why a real .github/workflows file passes through unchanged.
    `manual` -> `workflow_dispatch` is an event *value*, not a key — the
    builder handles it, not this pass.
    """
    raise NotImplementedError
