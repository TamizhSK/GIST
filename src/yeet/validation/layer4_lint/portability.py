"""Lint rules for cross-platform portability (W409, W410).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import re
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register

ABSOLUTE_PATH_PATTERN = re.compile(r"(/home/[^\s\"']+|/Users/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)")


class PortabilityRule:
    code = "YEET-W409"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return diags

        for idx, line in enumerate(content.splitlines()):
            match = ABSOLUTE_PATH_PATTERN.search(line)
            if match:
                diags.append(
                    Diagnostic(
                        code="YEET-W409",
                        severity=Severity.WARNING,
                        message=f"Absolute host path detected: `{match.group(1)}`",
                        file=path,
                        pos=Position(line=idx, col=0),
                        help="Use relative paths or `${{ github.workspace }}` variables",
                    )
                )

        return diags


register(PortabilityRule())
