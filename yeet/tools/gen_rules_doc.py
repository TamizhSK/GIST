#!/usr/bin/env python3
"""Generates docs/rules.md from core/codes.py so the doc and code never drift.

Owner: Dev D / Task D18
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure yeet package can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yeet.core.codes import RULES, Rule

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "rules.md"

HEADER = """# yeet Diagnostic Rules Reference

*Auto-generated from `src/yeet/core/codes.py` — do not hand-edit.*

This document lists all diagnostic codes emitted by `yeet` during validation and linting.

"""


def generate_rules_markdown() -> str:
    lines = [HEADER]

    # Group rules by layer
    layer_names = {
        0: "Layer 0 — File & Encoding",
        1: "Layer 1 — YAML Syntax",
        2: "Layer 2 — Schema Validation",
        3: "Layer 3 — Semantic Validation",
        4: "Layer 4 — Lint & Code Standards",
    }

    rules_by_layer: dict[int, list[Rule]] = {layer: [] for layer in layer_names}
    for rule in RULES.values():
        rules_by_layer.setdefault(rule.layer, []).append(rule)

    for layer_id, layer_title in layer_names.items():
        layer_rules = rules_by_layer.get(layer_id, [])
        if not layer_rules:
            continue

        lines.append(f"## {layer_title}\n")
        lines.append("| Code | Default Severity | Title |")
        lines.append("|---|---|---|")

        for r in layer_rules:
            anchor = r.code.lower()
            lines.append(f"| [`{r.code}`](#{anchor}) | `{r.default_severity.value}` | {r.title} |")

        lines.append("\n---\n")

        for r in layer_rules:
            lines.append(f"### `{r.code}` — {r.title}\n")
            lines.append(f"- **Layer:** {r.layer} ({layer_title})")
            lines.append(f"- **Default Severity:** `{r.default_severity.value}`")
            lines.append(f"- **Meaning:** {r.title}.")
            lines.append("\n```yaml\n# Example triggering pattern\n# ...\n```\n")
            lines.append("---\n")

    return "\n".join(lines)


def main() -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = generate_rules_markdown()
    DOC_PATH.write_text(content, encoding="utf-8")
    print(f"Successfully generated {DOC_PATH}")


if __name__ == "__main__":
    main()
