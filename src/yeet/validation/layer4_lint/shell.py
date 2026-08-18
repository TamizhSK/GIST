"""Lint rules for shell execution (W405, W406, W408).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register


class ShellRule:
    code = "YEET-W405"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        for job_id, job in wf.jobs.items():
            is_deploy = "deploy" in job_id.lower() or "publish" in job_id.lower()

            for step in job.steps:
                if step.continue_on_error and is_deploy:
                    diags.append(
                        Diagnostic(
                            code="YEET-W408",
                            severity=Severity.WARNING,
                            message=f"`continue-on-error: true` set on deploy job `{job_id}`",
                            file=path,
                            pos=step.pos or Position(line=0, col=0),
                            help="Avoid ignoring errors in deployment jobs",
                        )
                    )

                if step.run:
                    lines = step.run.strip().splitlines()
                    if len(lines) > 50:
                        diags.append(
                            Diagnostic(
                                code="YEET-W406",
                                severity=Severity.WARNING,
                                message=f"Run step has {len(lines)} lines (> 50 lines limit)",
                                file=path,
                                pos=step.pos or Position(line=0, col=0),
                                help="Extract long scripts into dedicated script files",
                            )
                        )

                    no_safe = not any("set -e" in line or "pipefail" in line for line in lines[:3])
                    if len(lines) > 1 and no_safe:
                        diags.append(
                            Diagnostic(
                                code="YEET-W405",
                                severity=Severity.WARNING,
                                message="Multi-line `run:` lacks `set -euo pipefail` header",
                                file=path,
                                pos=step.pos or Position(line=0, col=0),
                                help="Add `set -euo pipefail` at top of bash script",
                            )
                        )

        return diags


register(ShellRule())
