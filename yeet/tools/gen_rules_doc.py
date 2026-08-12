#!/usr/bin/env python3
"""Generates docs/rules.md from core/codes.py so the doc and code never drift.

Run it with `make rules`. CI regenerates and diffs, so a rule added to
`codes.py` without regenerating is a red build rather than a stale document.

Where the triggering examples come from: `tests/invalid/<CODE>.yml`. Those
fixtures already exist, each is broken in exactly one way, and the corpus test
asserts each one emits exactly its own code — so embedding them here means the
example in the docs is verified by the test suite rather than written by hand
and left to rot.

Owner: Dev D / Task D18
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from yeet.core.codes import RULES, Rule  # noqa: E402

DOC_PATH = ROOT / "docs" / "rules.md"
INVALID_DIR = ROOT / "tests" / "invalid"

HEADER = """# yeet Diagnostic Rules Reference

*Auto-generated from `src/yeet/core/codes.py` by `tools/gen_rules_doc.py` —
do not hand-edit. Run `make rules` after adding a code.*

Every diagnostic yeet can emit. `yeet explain YEET-E301` prints one section.

- **E**rrors block: `yeet check` exits 2 and `yeet run` refuses to start.
- **W**arnings print and do not block, unless `--strict` or a `.yeet/lint.yml`
  override promotes them.
- **I**nfo is advisory only.

Layer 4 codes can be reconfigured per project in `.yeet/lint.yml`:

```yaml
YEET-W403: error    # promote — now blocks
YEET-W407: off      # silence entirely
```

"""

LAYER_NAMES = {
    0: "Layer 0 — File & Encoding",
    1: "Layer 1 — YAML Syntax",
    2: "Layer 2 — Schema Validation",
    3: "Layer 3 — Semantic Validation",
    4: "Layer 4 — Lint & Code Standards",
    9: "Internal — bugs in yeet itself",
}


def _layer_title(layer: int) -> str:
    """Never drop a rule just because its layer is new.

    The previous version iterated a fixed 0-4 map, so a code registered at any
    other layer vanished from the docs silently — and `yeet explain` reads this
    file, so the code would exist, fire, and have no documentation anywhere.
    """
    return LAYER_NAMES.get(layer, f"Layer {layer}")


def _example_for(code: str) -> str | None:
    """The invalid fixture for this code, if the corpus has one."""
    short = code.removeprefix("YEET-")
    fixture = INVALID_DIR / f"{short}.yml"
    if not fixture.is_file():
        return None
    return fixture.read_text(encoding="utf-8").strip()


def _disable_hint(rule: Rule) -> str:
    if rule.layer == 4:
        return (
            f"Set `{rule.code}: off` in `.yeet/lint.yml` to silence it, "
            f"or `{rule.code}: error` to make it blocking."
        )
    if rule.layer == 9:
        return "Not configurable — this reports a fault in yeet, not in your workflow."
    return (
        "Not configurable: layers 0-3 are correctness checks, and a workflow "
        "that fails one of them cannot be run faithfully."
    )


def generate_rules_markdown() -> str:
    lines = [HEADER]

    rules_by_layer: dict[int, list[Rule]] = {}
    for rule in RULES.values():
        rules_by_layer.setdefault(rule.layer, []).append(rule)

    for layer_id in sorted(rules_by_layer):
        layer_rules = sorted(rules_by_layer[layer_id], key=lambda r: r.code)
        layer_title = _layer_title(layer_id)

        lines.append(f"## {layer_title}\n")
        lines.append("| Code | Default Severity | Title |")
        lines.append("|---|---|---|")
        for r in layer_rules:
            lines.append(f"| [`{r.code}`](#{r.code.lower()}) | `{r.default_severity.value}` | {r.title} |")
        lines.append("\n---\n")

        for r in layer_rules:
            lines.append(f"### `{r.code}` — {r.title}\n")
            lines.append(f"- **Layer:** {r.layer} ({layer_title})")
            lines.append(f"- **Default severity:** `{r.default_severity.value}`")
            lines.append(f"- **Meaning:** {r.title}.")
            lines.append(f"- **Disabling:** {_disable_hint(r)}\n")

            example = _example_for(r.code)
            if example:
                lines.append("A workflow that triggers it — "
                             f"`tests/invalid/{r.code.removeprefix('YEET-')}.yml`:\n")
                lines.append(f"```yaml\n{example}\n```\n")
            lines.append("---\n")

    return "\n".join(lines)


def main() -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(generate_rules_markdown(), encoding="utf-8")
    sys.stdout.write(f"wrote {DOC_PATH.relative_to(ROOT)} ({len(RULES)} rules)\n")


if __name__ == "__main__":
    main()
