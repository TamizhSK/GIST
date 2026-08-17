#!/usr/bin/env python3
"""Risk register #2: no bare `print()` under src/.

Everything the user sees is either a `Diagnostic` (validation) or a
`typer.echo`/`typer.secho` (CLI). The failure mode this guards against is a
hurried `print(f"bad key: {k}")` in the parser that nobody notices until it is
in front of an audience — it bypasses `--format json`, `--no-color`, stderr
routing and the diagnostic codes all at once.

This walks the AST rather than grepping, because a grep also matches the word
`print(` inside a docstring — `core/diagnostics.py` opens with "Nobody calls
print() for an error. Ever.", and a check that has to be worked around on its
first run is a check people delete.

Usage: python tools/check_no_print.py [path ...]   (default: src)
Exit 0 clean, 1 with one `path:line` per offence.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def offences(tree: ast.AST) -> list[int]:
    """Line numbers of calls to the builtin `print`."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            found.append(node.lineno)
    return found


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [ROOT / "src"]
    bad: list[str] = []

    for target in targets:
        files = sorted(target.rglob("*.py")) if target.is_dir() else [target]
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                sys.stderr.write(f"could not parse {path}: {exc}\n")
                return 1
            for line in offences(tree):
                rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
                bad.append(f"{rel}:{line}")

    if bad:
        sys.stderr.write("Bare print() under src/ — risk register #2:\n")
        for entry in bad:
            sys.stderr.write(f"  {entry}\n")
        sys.stderr.write(
            "\nUser-facing output is a Diagnostic (validation layers) or "
            "typer.echo/typer.secho (CLI commands).\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
