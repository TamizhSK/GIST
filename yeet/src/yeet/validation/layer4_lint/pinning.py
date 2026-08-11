"""Lint rules for pinning and action versions (W402, W403, W411, W412).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register


class PinningRule:
    code = "YEET-W402"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        for job_id, job in wf.jobs.items():
            # Check container image tag
            is_latest = job.container_image and job.container_image.endswith(":latest")
            if job.runs_on == "ubuntu-latest" or is_latest:
                diags.append(
                    Diagnostic(
                        code="YEET-W403",
                        severity=Severity.WARNING,
                        message=f"Job `{job_id}` uses image/tag `:latest`",
                        file=path,
                        pos=job.pos or Position(line=0, col=0),
                        help="Pin container images to specific version tags",
                    )
                )

            for step in job.steps:
                if step.uses:
                    ref = step.uses.split("@")[-1] if "@" in step.uses else ""
                    if ref in ("main", "master", "latest", "head", "v1", "v2"):
                        diags.append(
                            Diagnostic(
                                code="YEET-W402",
                                severity=Severity.WARNING,
                                message=f"Action `{step.uses}` is pinned to moving ref `@{ref}`",
                                file=path,
                                pos=step.pos or Position(line=0, col=0),
                                help="Pin action to full commit SHA for reproducible builds",
                            )
                        )

                if step.run:
                    for line in step.run.splitlines():
                        if any(c in line for c in ("::set-output", "::save-state", "::set-env")):
                            diags.append(
                                Diagnostic(
                                    code="YEET-W411",
                                    severity=Severity.WARNING,
                                    message="Deprecated workflow command in step run",
                                    file=path,
                                    pos=step.pos or Position(line=0, col=0),
                                    help="Use `$GITHUB_OUTPUT` or `$GITHUB_ENV` files instead",
                                )
                            )

        return diags


register(PinningRule())
