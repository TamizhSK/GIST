"""Typer app. Wires subcommands. Owns exit codes: 0 ok, 1 job failed, 2 bad file, 3 no docker.

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
