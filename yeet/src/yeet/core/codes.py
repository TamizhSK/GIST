"""The diagnostic code registry — single source of truth.

Adding a rule = add a row here + implement it + add tests/invalid/<CODE>.yml.
docs/rules.md is GENERATED from this table, so it can never drift.

Ranges:  E0xx file · E1xx yaml · E2xx schema · E3xx semantic · W4xx lint · I4xx info

Owner: Dev D (but everyone adds rows)
Tier: 0
"""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Severity

PREFIX = "YEET"


@dataclass(frozen=True, slots=True)
class Rule:
    code: str
    default_severity: Severity
    title: str
    layer: int


def _e(code: str, title: str, layer: int) -> Rule:
    return Rule(f"{PREFIX}-{code}", Severity.ERROR, title, layer)


def _w(code: str, title: str, layer: int) -> Rule:
    return Rule(f"{PREFIX}-{code}", Severity.WARNING, title, layer)


# Seed set. Fill the rest in from docs/architecture.md §3.10 as you implement.
RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # Layer 0 — file & encoding
        _e("E002", "file is empty", 0),
        _e("E005", "tabs used for indentation", 0),
        _w("W006", "CRLF line endings", 0),
        # Layer 1 — yaml
        _e("E101", "YAML parse failure", 1),
        _e("E102", "duplicate key", 1),
        _e("E103", "top-level document is not a mapping", 1),
        _w("W105", "unquoted `on` parsed as a boolean", 1),
        # Layer 2 — schema
        _e("E201", "unknown key", 2),
        _e("E202", "required key missing", 2),
        _e("E204", "step has both `run` and `uses`", 2),
        _e("E205", "step has neither `run` nor `uses`", 2),
        # Layer 3 — semantic
        _e("E301", "`needs` references an unknown job", 3),
        _e("E302", "dependency cycle", 3),
        _e("E309", "expression fails to parse", 3),
        # Layer 4 — lint / standards
        _w("W401", "missing name", 4),
        _w("W402", "action pinned to a moving ref", 4),
        _w("W404", "possible hardcoded secret", 4),
        _w("W407", "job has no timeout", 4),
    ]
}


def get(code: str) -> Rule:
    key = code if code.startswith(PREFIX) else f"{PREFIX}-{code}"
    if key not in RULES:
        raise KeyError(f"unregistered diagnostic code: {code}")
    return RULES[key]
