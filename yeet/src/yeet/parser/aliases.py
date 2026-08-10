"""Load aliases.yml; rewrite dialect keys to canonical ones. Sets used_dialect.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def normalize(node: object) -> object:
    """Recursive key rewrite. Preserves ruamel position data — do not rebuild dicts naively."""
    raise NotImplementedError
