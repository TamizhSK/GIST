"""Rule protocol + registry + .yeet/lint.yml severity overrides.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from yeet.core.diagnostics import Diagnostic, DiagnosticBag
from yeet.core.ir import Workflow


@runtime_checkable
class LintRule(Protocol):
    """A rule is anything with a code and a check(). Adding one is a new file
    plus a @register — never an edit to a dispatch table someone else owns."""

    code: str

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]: ...


RULES: list[LintRule] = []


def register(rule: LintRule) -> LintRule:
    RULES.append(rule)
    return rule


def run_lints(wf: Workflow, path: Path, cfg: dict[str, str]) -> DiagnosticBag:
    """Run every registered rule and apply `.yeet/lint.yml` severity overrides.

    `cfg` comes from `core.config.load_lint_config`: {"YEET-W403": "error",
    "YEET-W407": "off"}. Layer 4 never blocks unless --strict, so a rule
    promoted to "error" here still only blocks under --strict.
    """
    raise NotImplementedError
