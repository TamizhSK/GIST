"""Load aliases.yml; rewrite dialect keys to canonical ones. Sets used_dialect.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _Scope:
    """One position in a workflow, and what its keys mean there.

    `rewrite`: are this mapping's keys SCHEMA keys, or user data? Job IDs,
    env var names, matrix variables and action inputs are all user data sitting
    at key position, and rewriting them is a silent mistranslation — the one
    failure mode a local runner must never have.

    `children`: canonical key -> the scope its value opens. Everything absent
    is `opaque`, so a new schema key defaults to "do not touch", which is the
    safe direction to be wrong in.
    """

    rewrite: bool
    children: dict[str, str]


#: Only these positions hold schema keys. `matrix:`, `with:`, `env:`,
#: `secrets:`, `outputs:`, `on:` and `permissions:` are reached through the
#: `opaque` default and are left exactly as the user wrote them.
_SCOPES: dict[str, _Scope] = {
    "opaque": _Scope(rewrite=False, children={}),
    "workflow": _Scope(rewrite=True, children={"jobs": "jobs", "defaults": "defaults"}),
    # Keys here are job IDs. A job called `after` must stay called `after`.
    "jobs": _Scope(rewrite=False, children={}),
    "job": _Scope(
        rewrite=True,
        children={
            "strategy": "strategy",
            "steps": "step",
            "container": "container",
            "services": "services",
            "defaults": "defaults",
        },
    ),
    "step": _Scope(rewrite=True, children={}),
    "strategy": _Scope(rewrite=True, children={}),
    "container": _Scope(rewrite=True, children={}),
    # Keys here are service IDs; each value is a container.
    "services": _Scope(rewrite=False, children={}),
    "defaults": _Scope(rewrite=True, children={"run": "defaults_run"}),
    "defaults_run": _Scope(rewrite=True, children={}),
}

#: What an unlisted child of a user-keyed mapping opens. `jobs` -> `job`,
#: `services` -> `container`; everything else stays opaque.
_ELEMENT_SCOPE = {"jobs": "job", "services": "container"}


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


@dataclass(frozen=True, slots=True)
class Collision:
    """Two spellings of one key in the same mapping. See `find_collisions`."""

    canonical: str
    spellings: tuple[str, ...]
    line: int
    col: int


def find_collisions(node: Any) -> list[Collision]:
    """Mappings where two keys normalize to the same canonical key.

    RUN THIS BEFORE `normalize()`. The rewrite is `mapping[new] =
    mapping.pop(old)`, so a file containing both `name:` and `vibe:` loses one
    of them with no diagnostic at all — the tool silently ran a workflow the
    user did not write. Both spellings are legal everywhere, in any file, in
    any directory; what is not legal is spelling the SAME key twice and
    expecting us to guess which one was meant.

    Alias-vs-alias counts too: `bet:` and `cook:` are both `run`.

    Reported as an error rather than resolved by precedence because there is no
    honest precedence to pick. `name:` first in the file is not more intentional
    than `vibe:` second, and quietly dropping either is the failure mode this
    whole function exists to remove.
    """
    aliases = _load_aliases()
    found: list[Collision] = []
    _collect_collisions(node, aliases, found)
    return found


def _collect_collisions(
    node: Any, aliases: dict[str, str], found: list[Collision], scope: str = "workflow"
) -> None:
    """The same walk `_rewrite` takes, so the two cannot disagree about where a
    key is a key. `with: {name: a, vibe: b}` is two action inputs, not a
    collision, and reporting it as one would refuse a valid workflow."""
    if isinstance(node, list):
        for item in node:
            _collect_collisions(item, aliases, found, scope)
        return
    if not isinstance(node, CommentedMap):
        return
    here = _SCOPES.get(scope, _SCOPES["opaque"])
    if here.rewrite:
        by_target: dict[str, list[str]] = {}
        for key in node:
            if isinstance(key, str):
                by_target.setdefault(aliases.get(key, key), []).append(key)
        for canonical, spellings in by_target.items():
            if len(spellings) > 1:
                line, col = _key_pos(node, spellings[-1])
                found.append(Collision(canonical, tuple(spellings), line, col))
    for key, value in node.items():
        _collect_collisions(value, aliases, found, _child_scope(here, scope, key, aliases))


def _key_pos(mapping: CommentedMap, key: str) -> tuple[int, int]:
    """Point at the LATER spelling — the one whose value currently wins."""
    try:
        line, col = mapping.lc.key(key)
    except (AttributeError, KeyError, TypeError):
        return -1, -1
    return int(line), int(col)


def normalize(node: Any) -> tuple[Any, bool]:
    """Recursive key rewrite. Returns (tree, used_dialect).

    Preserves ruamel position data — rewrite keys in place, do NOT rebuild the
    mappings naively or every diagnostic downstream loses its line number.

    Rewrites ONLY at the positions where a key is a schema key. `with:`,
    `env:`, `matrix:`, `secrets:`, `outputs:` and the job IDs under `jobs:`
    hold user data at key position, and a blind walk rewrote those too: a
    canonical GitHub Actions file with an input named `when:` came out with
    `on:`, ran differently than it was written, and reported itself as dialect.
    `_SCOPES` is the map of where the rewrite is allowed to look.

    `manual` -> `workflow_dispatch` is an event *value*, not a key — the
    builder handles it, not this pass.
    """
    aliases = _load_aliases()
    return node, _rewrite(node, aliases)


def _rewrite(node: Any, aliases: dict[str, str], scope: str = "workflow") -> bool:
    """Rewrite keys in place; return True if any alias was applied."""
    if isinstance(node, list):
        return any([_rewrite(item, aliases, scope) for item in node])
    if not isinstance(node, CommentedMap):
        return False
    here = _SCOPES.get(scope, _SCOPES["opaque"])
    used = False
    if here.rewrite:
        for key in list(node.keys()):
            if isinstance(key, str) and key in aliases:
                rename_key(node, key, aliases[key])
                used = True
    # After the rename, so children are looked up by their canonical name.
    for key, value in node.items():
        if _rewrite(value, aliases, _child_scope(here, scope, key, aliases)):
            used = True
    return used


def _child_scope(here: _Scope, scope: str, key: Any, aliases: dict[str, str]) -> str:
    """The scope `key`'s value opens, from inside `scope`."""
    if not here.rewrite:
        return _ELEMENT_SCOPE.get(scope, "opaque")
    if not isinstance(key, str):
        return "opaque"
    return here.children.get(aliases.get(key, key), "opaque")


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
