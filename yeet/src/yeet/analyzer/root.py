"""Walk UPWARD for .git / .yeet / .github/workflows / any ecosystem manifest.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path


def find_root(start: Path) -> Path:
    """Stop at filesystem root or $HOME. Never shell out to git.

    Priority: .git/ -> .yeet/ -> .github/workflows/ -> any marker file. The
    requirement explicitly includes projects the user just created locally, so
    a directory with two files in it and no VCS must still resolve.
    """
    raise NotImplementedError
