"""Load aliases.yml; rewrite dialect keys to canonical ones. Sets used_dialect.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

ALIAS_FILE = Path(__file__).with_name("aliases.yml")

# `manual` -> `workflow_dispatch` is an event *value*, not a key. Rewriting a
# key named `manual` would corrupt a workflow that legitimately used one; the
# builder translates the value `manual` under `when:`/`on:` instead.
_EXCLUDED_KEYS = frozenset({"manual"})

_ALIASES: dict[str, str] | None = None


def _load_aliases() -> dict[str, str]:
    """Load aliases.yml once. Never fails — a broken table must not take down
    the parser with it."""
    global _ALIASES
    if _ALIASES is None:
        try:
            data = YAML(typ="rt").load(ALIAS_FILE.read_text(encoding="utf-8"))
            keys = data.get("keys", {})
            _ALIASES = {k: v for k, v in keys.items() if k not in _EXCLUDED_KEYS}
        except Exception:  # noqa: BLE001 - this function must never raise
            _ALIASES = {}
    return _ALIASES


def alias_keys() -> list[str]:
    """The dialect aliases users may write, for did-you-mean suggestions.

    `manual` is deliberately absent — it is an event *value* handled by the
    builder, never a workflow key, so suggesting it for a typo'd key would be
    wrong.
    """
    return sorted(_load_aliases())


def alias_map() -> dict[str, str]:
    """alias -> canonical, for reverse lookups. Never fails (empty on error)."""
    return dict(_load_aliases())


def normalize(node: Any) -> tuple[Any, bool]:
    """Recursive key rewrite. Returns (tree, used_dialect).

    Preserves ruamel position data — rewrite keys in place, do NOT rebuild the
    mappings naively or every diagnostic downstream loses its line number.

    This function never fails and never warns: it is a pure key rewrite, which
    is exactly why a real .github/workflows file passes through unchanged.
    `manual` -> `workflow_dispatch` is an event *value*, not a key — the
    builder handles it, not this pass.
    """
    aliases = _load_aliases()
    return node, _rewrite(node, aliases)


def _rewrite(node: Any, aliases: dict[str, str]) -> bool:
    """Rewrite keys in place; return True if any alias was applied."""
    if isinstance(node, CommentedMap):
        used = False
        for key in list(node.keys()):
            if isinstance(key, str) and key in aliases:
                rename_key(node, key, aliases[key])
                used = True
        for value in node.values():
            if _rewrite(value, aliases):
                used = True
        return used
    if isinstance(node, list):
        used = False
        for item in node:
            if _rewrite(item, aliases):
                used = True
        return used
    return False


def rename_key(mapping: CommentedMap, old: Any, new: str) -> None:
    """In-place key rename that preserves ruamel position data.

    A naive `mapping[new] = mapping.pop(old)` rebuilds the mapping and every
    `.lc.key()`/`.lc.value()` lookup downstream loses its line number. ruamel
    keeps positions in `mapping.lc.data` keyed by the key value, so the rename
    must move that entry too. Shared with `loader.load_with_positions` for the
    W105 `True -> "on"` fix.
    """
    value = mapping.pop(old)
    mapping[new] = value
    if (
        getattr(mapping, "lc", None) is not None
        and mapping.lc.data is not None
        and old in mapping.lc.data
    ):
        mapping.lc.data[new] = mapping.lc.data.pop(old)
