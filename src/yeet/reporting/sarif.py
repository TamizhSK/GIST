"""SARIF 2.1.0 diagnostic formatter.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import json
from typing import Any

from yeet.core.diagnostics import DiagnosticBag, Severity


def to_sarif(bag: DiagnosticBag) -> str:
    """Format DiagnosticBag into SARIF v2.1.0 standard JSON."""
    results: list[dict[str, Any]] = []

    for diag in bag.sorted():
        level = (
            "error"
            if diag.severity == Severity.ERROR
            else ("warning" if diag.severity == Severity.WARNING else "note")
        )
        result: dict[str, Any] = {
            "ruleId": diag.code,
            "level": level,
            "message": {"text": diag.message},
        }

        if diag.file:
            location: dict[str, Any] = {
                "physicalLocation": {"artifactLocation": {"uri": diag.file.as_posix()}}
            }
            if diag.pos and diag.pos.is_known:
                region: dict[str, Any] = {
                    "startLine": diag.pos.line + 1,
                    "startColumn": diag.pos.col + 1,
                }
                if diag.pos.end_col is not None:
                    region["endColumn"] = diag.pos.end_col + 1
                location["physicalLocation"]["region"] = region

            result["locations"] = [location]

        results.append(result)

    sarif_doc = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "yeet",
                        "informationUri": "https://github.com/TamizhSK/YEET",
                    }
                },
                "results": results,
            }
        ],
    }

    return json.dumps(sarif_doc, indent=2)
