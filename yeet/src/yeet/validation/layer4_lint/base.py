"""Rule protocol + registry + .yeet/lint.yml severity overrides.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Severity
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
    bag = DiagnosticBag()

    for rule in RULES:
        code_key = rule.code if rule.code.startswith("YEET-") else f"YEET-{rule.code}"

        # Check if rule is disabled in config
        override = cfg.get(code_key, "").lower()
        if override == "off":
            continue

        try:
            diags = rule.check(wf, path)
        except Exception:
            continue

        for diag in diags:
            diag_code = diag.code if diag.code.startswith("YEET-") else f"YEET-{diag.code}"
            single_override = cfg.get(diag_code, "").lower()

            if single_override == "off":
                continue

            sev = diag.severity
            if single_override == "error":
                sev = Severity.ERROR
            elif single_override == "warning":
                sev = Severity.WARNING
            elif single_override == "info":
                sev = Severity.INFO

            new_diag = Diagnostic(
                code=diag.code,
                severity=sev,
                message=diag.message,
                file=diag.file,
                pos=diag.pos,
                help=diag.help,
                note=diag.note,
                url=diag.url,
            )
            bag.add(new_diag)

    return bag
