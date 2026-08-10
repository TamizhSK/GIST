"""Walk UPWARD for .git / .yeet / .github/workflows / any ecosystem manifest.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

def find_root(start: Path) -> Path:
    """Stop at filesystem root or $HOME. Never shell out to git."""
    raise NotImplementedError
