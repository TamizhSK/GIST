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


def _i(code: str, title: str, layer: int) -> Rule:
    return Rule(f"{PREFIX}-{code}", Severity.INFO, title, layer)


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # Layer 0 — file & encoding
        _e("E001", "file unreadable or missing", 0),
        _e("E002", "file is empty", 0),
        _e("E003", "non-UTF-8 character encoding", 0),
        _w("W004", "UTF-8 BOM present", 0),
        _e("E005", "tabs used for indentation", 0),
        _w("W006", "CRLF line endings", 0),
        _w("W007", "file size exceeds 1 MB", 0),
        # Layer 1 — yaml
        _e("E101", "YAML parse failure", 1),
        _e("E102", "duplicate key", 1),
        _e("E103", "top-level document is not a mapping", 1),
        _e("E104", "multi-document YAML is not allowed", 1),
        _w("W105", "unquoted `on` parsed as a boolean", 1),
        # Layer 2 — schema
        _e("E201", "unknown key", 2),
        _e("E202", "required key missing", 2),
        _e("E203", "invalid data type", 2),
        _e("E204", "step has both `run` and `uses`", 2),
        _e("E205", "step has neither `run` nor `uses`", 2),
        _e("E206", "invalid event name", 2),
        _e("E207", "invalid job id", 2),
        _e("E208", "empty step list", 2),
        # Layer 3 — semantic
        _e("E301", "`needs` references an unknown job", 3),
        _e("E302", "dependency cycle", 3),
        _e("E303", "invalid matrix configuration", 3),
        _e("E304", "duplicate job id", 3),
        _e("E305", "invalid environment variable name", 3),
        _e("E306", "invalid container image format", 3),
        _e("E307", "missing secret reference", 3),
        _e("E308", "invalid action reference", 3),
        _e("E309", "expression fails to parse", 3),
        _e("E310", "expression references unknown context", 3),
        _e("E311", "expression references unknown function", 3),
        _e("E312", "invalid expression position", 3),
        _e("E313", "missing required action input", 3),
        _e("E314", "unknown action input", 3),
        _e("E315", "`cooked_on:` could not be resolved to an image", 3),
        _e("E316", "invalid runner specification", 3),
        _w("W317", "deprecated workflow syntax", 3),
        _w("W318", "unused output variable", 3),
        _w("W319", "action version mismatch", 3),
        # Layer 4 — lint / standards
        _w("W401", "missing name", 4),
        _w("W402", "action pinned to a moving ref", 4),
        _w("W403", "image pinned to :latest tag", 4),
        _w("W404", "possible hardcoded secret", 4),
        _w("W405", "multi-line run without `set -euo pipefail`", 4),
        _w("W406", "run step exceeds 50 lines", 4),
        _w("W407", "job has no timeout", 4),
        _w("W408", "continue-on-error on deploy job", 4),
        _w("W409", "absolute host path in workflow", 4),
        _w("W410", "path case mismatch with disk", 4),
        _w("W411", "deprecated command format", 4),
        _w("W412", "EOL action version", 4),
        _w("W413", "zero steps in job", 4),
        _w("W414", "duplicated step block across jobs", 4),
        _i("I415", "mixed dialect and canonical keys", 4),
    ]
}


def get(code: str) -> Rule:
    key = code if code.startswith(PREFIX) else f"{PREFIX}-{code}"
    if key not in RULES:
        raise KeyError(f"unregistered diagnostic code: {code}")
    return RULES[key]
