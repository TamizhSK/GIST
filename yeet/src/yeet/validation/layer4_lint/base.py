"""Rule protocol + registry + .yeet/lint.yml severity overrides.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

RULES: list["LintRule"] = []


def register(rule: "LintRule") -> "LintRule":
    RULES.append(rule)
    return rule
