"""jsonschema against workflow.schema.json; best_match + readable JSON paths.

Owner: Dev A
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yeet.core.diagnostics import DiagnosticBag

SCHEMA_FILE = Path(__file__).parents[1] / "parser" / "schema" / "workflow.schema.json"


def check(data: Any, path: Path) -> DiagnosticBag:
    """E201-E208. Aliases are already normalized away — this validates the
    CANONICAL form only, which is why there is exactly one schema.

    jsonschema's default errors are unusable. Use
    `jsonschema.exceptions.best_match(validator.iter_errors(doc))` and turn
    `error.absolute_path` (a deque) into `jobs.build.steps[2].run`.
    """
    raise NotImplementedError
