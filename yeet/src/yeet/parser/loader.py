"""ruamel.yaml round-trip load. Emits E101/E102/E103/W105. KEEPS line+col.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import MarkedYAMLError

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.parser.aliases import rename_key

_EMPTY_MSG = "the file is empty — nothing to validate"


def load_with_positions(path: Path, bag: DiagnosticBag) -> Any | None:
    """YAML(typ='rt'); use .lc.key()/.lc.value() for every position.

    Returns None on E101/E103 — the caller must stop rather than schema-check
    a tree that never parsed. Subclass the constructor so duplicate keys RAISE
    (E102): PyYAML silently keeps the last one, and two `moves:` keys silently
    dropping half a workflow is a nightmare to debug.

    ruamel 0.19's round-trip constructor already raises DuplicateKeyError on
    duplicate mapping keys, so we catch it where a subclass would have thrown.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        bag.add(
            Diagnostic(
                code="YEET-E001",
                severity=Severity.ERROR,
                message=f"cannot read the file ({exc.strerror or exc})",
                file=path,
                pos=Position.unknown(),
            )
        )
        return None

    yaml = YAML(typ="rt")
    try:
        docs = list(yaml.load_all(text))
    except DuplicateKeyError as exc:
        bag.add(
            Diagnostic(
                code="YEET-E102",
                severity=Severity.ERROR,
                message="duplicate key — YAML keeps only the last one, so one of these "
                "is silently dropped",
                file=path,
                pos=_mark_pos(exc),
            )
        )
        return None
    except MarkedYAMLError as exc:
        bag.add(
            Diagnostic(
                code="YEET-E101",
                severity=Severity.ERROR,
                message=f"invalid YAML: {exc.problem or 'syntax error'}",
                file=path,
                pos=_mark_pos(exc),
            )
        )
        return None

    if not docs:
        bag.add(
            Diagnostic(
                code="YEET-E002",
                severity=Severity.ERROR,
                message=_EMPTY_MSG,
                file=path,
                pos=Position.unknown(),
            )
        )
        return None

    if len(docs) > 1:
        bag.add(
            Diagnostic(
                code="YEET-E104",
                severity=Severity.ERROR,
                message="multiple YAML documents in one file — keep exactly one",
                file=path,
                pos=_doc_pos(docs[1]),
            )
        )
        return None

    data = docs[0]
    if data is None:
        bag.add(
            Diagnostic(
                code="YEET-E002",
                severity=Severity.ERROR,
                message=_EMPTY_MSG,
                file=path,
                pos=Position.unknown(),
            )
        )
        return None

    if not isinstance(data, CommentedMap):
        bag.add(
            Diagnostic(
                code="YEET-E103",
                severity=Severity.ERROR,
                message="the top level of a workflow must be a mapping (key: value), "
                f"not a {_root_kind(data)}",
                file=path,
                pos=_root_pos(data),
            )
        )
        return None

    _normalize_on_key(data, path, bag)
    return data


def _mark_pos(exc: MarkedYAMLError) -> Position:
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return Position.unknown()
    return Position(mark.line, mark.column)


def _doc_pos(doc: Any) -> Position:
    lc = getattr(doc, "lc", None)
    if lc is not None and hasattr(lc, "line"):
        return Position(lc.line, lc.col)
    return Position.unknown()


def _root_kind(data: Any) -> str:
    from ruamel.yaml.comments import CommentedSeq

    if isinstance(data, (CommentedSeq, list)):
        return "list"
    if isinstance(data, str):
        return "string"
    return type(data).__name__.lower()


def _root_pos(data: Any) -> Position:
    lc = getattr(data, "lc", None)
    if lc is not None and hasattr(lc, "line"):
        return Position(lc.line, lc.col)
    return Position.unknown()


def _normalize_on_key(data: CommentedMap, path: Path, bag: DiagnosticBag) -> None:
    """W105 — the `on:` trap.

    GitHub Actions resolves `on:` as the string key; a tool that round-tripped
    the file through a YAML 1.1 resolver leaves a boolean `True` behind
    (PyYAML silently keeps the last one — and here the wrong one). Tolerate it
    the same way GitHub does: rename the key back to "on" and warn.
    """
    if True not in data:
        return
    bag.add(
        Diagnostic(
            code="YEET-W105",
            severity=Severity.WARNING,
            message="found a bare `True` key — the unquoted `on:` YAML 1.1 trap. Quote it: `on:`",
            file=path,
            pos=Position(*data.lc.key(True)),
        )
    )
    rename_key(data, True, "on")
