"""Every code the product can EMIT has a row in the registry.

THE BUG THIS EXISTS FOR. `executor/docker_backend.py` emitted `YEET-E321` — the
code a user sees when the daemon refuses to start their container, carrying the
"disk is full" / "no arm64 build" / "mounts denied" diagnosis — and there was no
row for it in `core/codes.py`. So `yeet explain YEET-E321`, run against a code
copied out of their own log, answered "Unknown diagnostic code", and
`docs/rules.md` (generated from the same table) had no section for it either.

The registry is the single source of truth for both. A code that can fire
without a row is one nobody can look up, and nothing was checking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from yeet.core.codes import PREFIX, RULES

SRC = Path(__file__).parents[2] / "src" / "yeet"

#: `YEET-E321` / `YEET-W405` as they appear in a string literal in the source.
CODE_IN_SOURCE = re.compile(rf'["\']({PREFIX}-[EWI]\d{{3}})["\']')

#: `codes.py` builds the codes from bare numbers, so it never matches the
#: pattern above, but exclude it explicitly rather than by luck.
EXCLUDE = {"core/codes.py"}


def _emitted_codes() -> dict[str, set[str]]:
    """Every `YEET-Xnnn` literal in the product, mapped to the files using it."""
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel in EXCLUDE:
            continue
        for code in CODE_IN_SOURCE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(code, set()).add(rel)
    return found


def test_every_emitted_code_is_registered() -> None:
    emitted = _emitted_codes()
    assert emitted, "the scan found no codes at all — the pattern has rotted"

    unregistered = {code: sorted(files) for code, files in emitted.items() if code not in RULES}
    assert not unregistered, (
        "these codes are emitted but have no row in core/codes.py, so "
        f"`yeet explain` and docs/rules.md cannot describe them: {unregistered}"
    )


@pytest.mark.parametrize("code", sorted(RULES))
def test_every_registered_code_can_be_explained(code: str) -> None:
    """`yeet explain` reads the generated doc; a row with no section is the
    same dead end from the other direction."""
    from yeet.core.codes import get

    rule = get(code)
    assert rule.title.strip()
    assert rule.code == code


def test_the_registry_and_the_generated_doc_agree() -> None:
    """`make rules` regenerates; CI diffs. This catches the gap locally first."""
    doc = (Path(__file__).parents[2] / "docs" / "rules.md").read_text(encoding="utf-8")
    missing = [code for code in RULES if f"### `{code}`" not in doc]
    assert not missing, f"docs/rules.md is stale — run `make rules`. Missing: {missing}"
