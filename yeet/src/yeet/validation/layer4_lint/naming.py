"""Lint rules for naming & structure (W401, W413, W414, I415).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register


class NamingRule:
    code = "YEET-W401"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        if not wf.name:
            diags.append(
                Diagnostic(
                    code="YEET-W401",
                    severity=Severity.WARNING,
                    message="Workflow has no `name:` top-level attribute",
                    file=path,
                    pos=wf.pos or Position(line=0, col=0),
                    help="Add a descriptive `name: ...` header",
                )
            )

        for job_id, job in wf.jobs.items():
            if not job.steps:
                diags.append(
                    Diagnostic(
                        code="YEET-W413",
                        severity=Severity.WARNING,
                        message=f"Job `{job_id}` has zero steps",
                        file=path,
                        pos=job.pos or Position(line=0, col=0),
                        help="Add at least one step to the job",
                    )
                )

            for step_idx, step in enumerate(job.steps):
                if not step.name and not step.uses:
                    diags.append(
                        Diagnostic(
                            code="YEET-W401",
                            severity=Severity.WARNING,
                            message=f"Step #{step_idx + 1} in `{job_id}` has no `name:` attribute",
                            file=path,
                            pos=step.pos or Position(line=0, col=0),
                            help="Add a `name:` for clearer build logs",
                        )
                    )

        return diags


register(NamingRule())
