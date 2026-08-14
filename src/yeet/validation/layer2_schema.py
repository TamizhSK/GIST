"""jsonschema against workflow.schema.json; best_match + readable JSON paths.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md

The schema validates structure and types only. Unknown keys, unknown events and
step run/uses are checked DIRECTLY here because jsonschema's errors for those
cases are unreadable (additionalProperties/propertyNames messages are noise).
That split is documented in workflow.schema.json's description field.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from jsonschema.protocols import Validator

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.parser.aliases import alias_map
from yeet.validation.suggest import did_you_mean

SCHEMA_FILE = Path(__file__).parents[1] / "parser" / "schema" / "workflow.schema.json"

_ID_PATTERN = "[A-Za-z_][A-Za-z0-9_-]*"

# The events yeet can actually trigger or simulate. `manual` is the dialect
# alias for workflow_dispatch and is valid as an `on:`/`when:` key.
SUPPORTED_EVENTS: frozenset[str] = frozenset(
    {
        "push",
        "pull_request",
        "pull_request_target",
        "pull_request_review",
        "pull_request_review_comment",
        "schedule",
        "workflow_dispatch",
        "workflow_call",
        "workflow_run",
        "repository_dispatch",
        "release",
        "create",
        "delete",
        "fork",
        "issues",
        "issue_comment",
        "label",
        "milestone",
        "page_build",
        "public",
        "status",
        "watch",
        "gollum",
        "discussion",
        "discussion_comment",
        "project",
        "project_card",
        "project_column",
        "check_run",
        "check_suite",
        "deployment",
        "deployment_status",
        "merge_group",
        "registry_package",
        "manual",
    }
)

_schema: dict[str, Any] | None = None
_validator: Validator | None = None


def _schema_data() -> dict[str, Any]:
    global _schema
    if _schema is None:
        _schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return _schema


def _get_validator() -> Validator:
    global _validator
    if _validator is None:
        _validator = Draft202012Validator(_schema_data())
    return _validator


def _allowed_keys(level: str) -> set[str]:
    """Canonical keys legal at a level, read from the schema itself."""
    schema = _schema_data()
    if level == "root":
        return set(schema.get("properties", {}))
    defn = schema["$defs"].get(level)
    if defn is None:
        return set()
    return set(defn.get("properties", {}))


def _alias_candidates(allowed: set[str]) -> set[str]:
    """allowed canonical keys + the dialect aliases that map into them."""
    aliases = alias_map()
    return allowed | {a for a, canon in aliases.items() if canon in allowed}


def _fmt_path(segs: Iterable[Any]) -> str:
    out = ""
    for seg in segs:
        if isinstance(seg, int):
            out += f"[{seg}]"
        else:
            out += f".{seg}" if out else str(seg)
    return out


def _node_at(node: Any, segs: list[Any]) -> Any:
    for s in segs:
        node = node[s]
    return node


def _key_pos(mapping: Any, key: Any) -> Position:
    lc = getattr(mapping, "lc", None)
    if lc is None:
        return Position.unknown()
    try:
        line, col = lc.key(key)
        return Position(line, col)
    except (KeyError, TypeError, ValueError):
        return Position.unknown()


def _err_position(data: Any, segs: list[Any], instance: Any = None) -> Position:
    """Position of the node a jsonschema error points at."""
    if instance is not None:
        segs = [*segs, instance]
    if not segs:
        return Position.unknown()
    try:
        parent = _node_at(data, segs[:-1])
        last = segs[-1]
        if isinstance(last, int):
            item = parent[last]
            lc = getattr(item, "lc", None)
            if lc is not None:
                return Position(lc.line, lc.col)
            return Position.unknown()
        return _key_pos(parent, last)
    except (KeyError, IndexError, TypeError):
        return Position.unknown()


_FRIENDLY: dict[type, str] = {
    dict: "a mapping",
    list: "a list",
    str: "a string",
    int: "an integer",
    float: "a number",
    bool: "a boolean",
    type(None): "null",
}


def _friendly(value: Any) -> str:
    return _FRIENDLY.get(type(value), type(value).__name__)


def _oneof_description(err: Any, field: str) -> str:
    """Readable expectation for a oneOf error on a known field."""
    if field in ("on", "when"):
        return "a string, a list, or a mapping of events"
    if field == "needs":
        return "a job name or a list of job names"
    best = best_match(err.context) if err.context else None
    if best is not None:
        return f"the wrong type — {best.message}"
    return "not valid under any of the allowed forms"


def check(data: Any, path: Path) -> DiagnosticBag:
    """E201, E202, E203, E206, E207, E208 (E204/E205 fire from builder, A16).

    Aliases are already normalized away — this validates the CANONICAL form
    only, which is why there is exactly one schema. All E-codes from a file are
    reported, never just the first: stopping within a layer is how you get a
    tool that makes the user fix one error per run.
    """
    bag = DiagnosticBag()
    _schema_errors(data, path, bag)
    _unknown_keys(data, path, bag)
    _unsupported_events(data, path, bag)
    return bag


def _schema_errors(data: Any, path: Path, bag: DiagnosticBag) -> None:
    for err in _get_validator().iter_errors(data):
        segs = list(err.absolute_path)
        v = err.validator
        loc = _fmt_path(segs)

        if v == "required":
            missing_keys = [str(k) for k in (err.validator_value or [])]
            if missing_keys:
                missing = ", ".join(f"`{k}`" for k in missing_keys[:-1])
                missing += f" and `{missing_keys[-1]}`" if missing else f"`{missing_keys[-1]}`"
            else:
                missing = "a required key"
            if loc:
                msg = f"missing required key {missing} in `{loc}`"
            else:
                msg = f"missing required key {missing}"
            bag.add(
                Diagnostic(
                    code="YEET-E202",
                    severity=Severity.ERROR,
                    message=msg,
                    file=path,
                    pos=_err_position(data, segs),
                    help="every workflow needs `on` and `jobs`; every job needs `steps`",
                )
            )

        elif v == "type":
            expected = err.validator_value
            if isinstance(expected, (list, tuple)):
                expected = " or ".join(str(t) for t in expected)
            actual = _friendly(err.instance)
            bag.add(
                Diagnostic(
                    code="YEET-E203",
                    severity=Severity.ERROR,
                    message=f"`{loc or 'workflow'}` should be {expected}, got {actual}",
                    file=path,
                    pos=_err_position(data, segs),
                )
            )

        elif v == "minProperties":
            bag.add(
                Diagnostic(
                    code="YEET-E206",
                    severity=Severity.ERROR,
                    message="no jobs defined — a workflow needs at least one job",
                    file=path,
                    pos=_err_position(data, segs),
                )
            )

        elif v == "pattern":
            if segs == ["jobs"] and isinstance(err.instance, str):
                bag.add(
                    Diagnostic(
                        code="YEET-E207",
                        severity=Severity.ERROR,
                        message=f"invalid job id `{err.instance}` — must match `{_ID_PATTERN}`",
                        file=path,
                        pos=_err_position(data, segs, err.instance),
                    )
                )
            elif segs and segs[-1] == "id" and isinstance(err.instance, str):
                bag.add(
                    Diagnostic(
                        code="YEET-E207",
                        severity=Severity.ERROR,
                        message=f"invalid step id `{err.instance}` — must match `{_ID_PATTERN}`",
                        file=path,
                        pos=_err_position(data, segs),
                    )
                )
            else:
                bag.add(
                    Diagnostic(
                        code="YEET-E207",
                        severity=Severity.ERROR,
                        message=err.message,
                        file=path,
                        pos=_err_position(data, segs),
                    )
                )

        elif v in ("oneOf", "anyOf"):
            field = str(segs[-1]) if segs else ""
            bag.add(
                Diagnostic(
                    code="YEET-E203",
                    severity=Severity.ERROR,
                    message=f"`{loc or 'workflow'}` should be {_oneof_description(err, field)}",
                    file=path,
                    pos=_err_position(data, segs),
                )
            )

        else:
            bag.add(
                Diagnostic(
                    code="YEET-E203",
                    severity=Severity.ERROR,
                    message=err.message or "workflow failed schema validation",
                    file=path,
                    pos=_err_position(data, segs),
                )
            )


def _unknown_keys(data: Any, path: Path, bag: DiagnosticBag) -> None:
    """E201 — unknown key at each level, with a did-you-mean suggestion."""

    def walk(node: Any, level: str) -> None:
        if not isinstance(node, (dict, list)):
            return
        if isinstance(node, list):
            for item in node:
                walk(item, level)
            return
        allowed = _allowed_keys(level)
        for key in list(node.keys()):
            if isinstance(key, str) and key not in allowed:
                candidates = _alias_candidates(allowed)
                suggestion = did_you_mean(key, candidates)
                bag.add(
                    Diagnostic(
                        code="YEET-E201",
                        severity=Severity.ERROR,
                        message=f"unknown key `{key}` here",
                        file=path,
                        pos=_key_pos(node, key),
                        help=f"did you mean `{suggestion}`?" if suggestion else None,
                    )
                )
        if level == "root" and isinstance(node.get("jobs"), dict):
            for job in node["jobs"].values():
                walk(job, "job")
        elif level == "job":
            steps = node.get("steps")
            if isinstance(steps, list):
                for step in steps:
                    walk(step, "step")
            if isinstance(node.get("strategy"), dict):
                walk(node["strategy"], "strategy")

    if isinstance(data, dict):
        walk(data, "root")


def _unsupported_events(data: Any, path: Path, bag: DiagnosticBag) -> None:
    """E208 — `on:`/`when:` names an event yeet doesn't support."""
    on_value = data.get("on") if isinstance(data, dict) else None
    if on_value is None:
        return

    if isinstance(on_value, str):
        names: list[Any] = [on_value]
        pos = _key_pos(data, "on")
    elif isinstance(on_value, list):
        names = list(on_value)
        pos = _key_pos(data, "on")
    elif isinstance(on_value, dict):
        names = list(on_value.keys())
        pos = Position.unknown()
    else:
        return

    supported = ", ".join(sorted(SUPPORTED_EVENTS - {"manual"}, key=lambda e: (e != "push", e)))
    for name in names:
        if not isinstance(name, str) or name in SUPPORTED_EVENTS:
            continue
        suggestion = did_you_mean(name, SUPPORTED_EVENTS)
        if isinstance(on_value, dict):
            pos = _key_pos(on_value, name)
        bag.add(
            Diagnostic(
                code="YEET-E208",
                severity=Severity.ERROR,
                message=f"unsupported event `{name}`",
                file=path,
                pos=pos,
                help=(f"did you mean `{suggestion}`?" if suggestion else f"supported: {supported}"),
            )
        )
