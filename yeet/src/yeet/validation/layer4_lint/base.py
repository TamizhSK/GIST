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
    "YEET-W407": "off"}.

    On what "error" in lint.yml actually does: it makes the diagnostic an
    ERROR, and `DiagnosticBag.exit_code()` returns 2 for any error, --strict or
    not. So promoting a lint to `error` in `.yeet/lint.yml` makes it blocking,
    full stop. (An earlier version of this docstring claimed it "still only
    blocks under --strict"; that was never true of the code, and a team relying
    on it would have shipped a workflow they thought was merely warned about.)
    --strict is the separate knob that makes plain *warnings* blocking.

    RULES is populated by importing the package, not this module — see
    `layer4_lint/__init__.py`.
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
        except Exception as exc:  # noqa: BLE001 - one bad rule must not kill the run
            # A crashing rule used to `continue` in silence, which meant a rule
            # could stop working and no one would find out. One rule must still
            # not take down the other nine, so it is caught — but reported.
            bag.add(
                Diagnostic(
                    code="YEET-E900",
                    severity=Severity.ERROR,
                    message=f"lint rule {rule.code} crashed: {exc!r}",
                    file=path,
                    help="This is a bug in the rule, not in your workflow. "
                    f"Disable it with `{code_key}: off` in .yeet/lint.yml "
                    "while it is fixed.",
                )
            )
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
