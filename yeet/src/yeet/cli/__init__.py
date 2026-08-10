"""CLI package. Exit codes live here so every command agrees on them.

Owner: Dev A
Tier: 7 — may import from: anything
"""

from __future__ import annotations

import typer

EXIT_OK = 0
"""slay"""
EXIT_JOB_FAILED = 1
"""the workflow ran and something in it failed"""
EXIT_BAD_WORKFLOW = 2
"""the workflow file is wrong — nothing ran. This is the validation gate."""
EXIT_NO_DOCKER = 3
"""no daemon. Distinct from 1 because a trainer may pipe this into something."""


def todo(command: str, owner: str) -> None:
    """Placeholder for an unimplemented command.

    Deliberately not a Diagnostic: this is scaffolding talking to the four of
    us, not the tool talking to a user about their file. Every one of these is
    gone by Friday.
    """
    typer.secho(
        f"`yeet {command}` is not implemented yet — owner: {owner}. See plan.md.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    # Exit 1, never 0: a placeholder must not look like success. `yeet check`
    # returning 0 on a broken workflow is exactly what the validation gate
    # exists to prevent, and a git hook or smoke test would believe it.
    # Not EXIT_JOB_FAILED or EXIT_BAD_WORKFLOW — neither is true here.
    raise typer.Exit(1)
