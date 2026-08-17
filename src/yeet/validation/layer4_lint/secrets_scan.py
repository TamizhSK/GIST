"""Lint rule for hardcoded secrets scanning (W404).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub Personal Access Token
    re.compile(r"gho_[A-Za-z0-9]{36}"),  # GitHub OAuth Token
    re.compile(r"glpat-[A-Za-z0-9\-]{20}"),  # GitLab Personal Access Token
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),  # Private keys
]


def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy (bits per character) of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    counts: dict[str, int] = {}
    for char in data:
        counts[char] = counts.get(char, 0) + 1
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


class SecretsScanRule:
    code = "YEET-W404"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        try:
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return diags

        lines = raw_text.splitlines()

        for idx, line in enumerate(lines):
            line_without_exprs = re.sub(r"\$\{\{\s*secrets\.[^\}]+\}\}", "", line)

            for pattern in SECRET_PATTERNS:
                if pattern.search(line_without_exprs):
                    diags.append(
                        Diagnostic(
                            code="YEET-W404",
                            severity=Severity.WARNING,
                            message="Possible hardcoded secret or token detected",
                            file=path,
                            pos=Position(line=idx, col=0),
                            help="Reference secret via `${{ secrets.NAME }}`",
                        )
                    )
                    break
            else:
                tokens = re.findall(r"['\"]([A-Za-z0-9_\-\+\/=]{20,})['\"]", line_without_exprs)
                for token in tokens:
                    if shannon_entropy(token) > 4.0:
                        diags.append(
                            Diagnostic(
                                code="YEET-W404",
                                severity=Severity.WARNING,
                                message="High-entropy string (possible secret)",
                                file=path,
                                pos=Position(line=idx, col=0),
                                help="Use secret expressions `${{ secrets.NAME }}`",
                            )
                        )
                        break

        return diags


register(SecretsScanRule())
