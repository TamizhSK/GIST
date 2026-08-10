"""difflib did-you-mean against canonical keys AND dialect aliases.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""
from __future__ import annotations

def did_you_mean(word: str, candidates: "Iterable[str]") -> str | None:
    raise NotImplementedError
