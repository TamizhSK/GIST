"""Lint rules for shell execution (W405, W406, W408).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Step, Workflow
from yeet.validation.layer4_lint.base import register

POSIX_SHELLS = ("bash", "sh")
"""The only shells `set -euo pipefail` means anything in.

W405 used to fire on every multi-line `run:` regardless of `shell:`, so a
`shell: pwsh`, `shell: python` or `shell: node` step was told to add a bash
builtin to the top of a script that is not bash. Following that advice breaks
the step; ignoring it trains people to ignore layer 4 altogether. Either way the
rule was wrong, and it was wrong on exactly the workflows that need the most
help — the cross-platform ones."""

_ALREADY_SAFE = ("-e", "pipefail")
"""`shell: bash -eo pipefail {0}` is GitHub's own way of saying "already safe".
A rule that then asks for `set -euo pipefail` in the body is asking twice."""


def effective_shell(step: Step, wf: Workflow) -> str:
    """The `shell:` this step actually gets — step, then workflow defaults.

    Empty means "nobody said", which is the runner's default: bash inside a
    container, which is where yeet runs everything that is not
    `cooked_on: local`. So an unset shell is treated as POSIX and the rule
    still fires on the ordinary case it was written for.
    """
    if step.shell:
        return step.shell.strip().lower()
    run_defaults: Any = wf.defaults.get("run") if isinstance(wf.defaults, dict) else None
    if isinstance(run_defaults, dict) and run_defaults.get("shell"):
        return str(run_defaults["shell"]).strip().lower()
    return ""


def wants_safety_header(shell: str) -> bool:
    """Would `set -euo pipefail` help this step, or break it?

    False for a non-POSIX shell, and false when the `shell:` line already
    carries the flags — `bash -eo pipefail {0}` has done the job already.
    """
    if not shell:
        return True
    first = shell.split()[0]
    if first not in POSIX_SHELLS:
        return False
    return not any(flag in shell for flag in _ALREADY_SAFE)


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
                    posix = wants_safety_header(effective_shell(step, wf))
                    if len(lines) > 1 and no_safe and posix:
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
