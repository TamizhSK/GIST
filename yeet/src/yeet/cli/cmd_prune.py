"""yeet prune — clear the build cache and old run scratch dirs.

Every edit to a Dockerfile mints a new content-hash tag and orphans the last
one. Left alone that is tens of gigabytes over a week of iteration, and the
user has no way to tell our images apart from theirs — ours all start with
`yeet-local/`, which is exactly what makes this command safe to write.

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from yeet.cli import EXIT_NO_DOCKER
from yeet.executor.backend import DockerUnavailable, get_docker_client
from yeet.executor.build import prune as prune_images
from yeet.executor.workspace import prune_tmp


def prune(
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    images: Annotated[
        bool, typer.Option("--images/--no-images", help="Remove built images.")
    ] = True,
) -> None:
    """Remove `yeet-local/*` images and every `.yeet/tmp/<run-id>/` directory.

    Never touches `.yeet/runs/` — those are the JSONL logs `yeet logs` replays,
    and silently deleting a user's run history to reclaim a few kilobytes would
    be a poor trade.
    """
    root = path.resolve()

    removed_dirs = prune_tmp(root)
    typer.echo(f"removed {removed_dirs} run scratch director{'y' if removed_dirs == 1 else 'ies'}")

    if not images:
        return

    try:
        client = get_docker_client()
    except DockerUnavailable as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(EXIT_NO_DOCKER) from exc

    removed = prune_images(client)
    for tag in removed:
        typer.echo(f"  removed {tag}")
    typer.echo(f"removed {len(removed)} image(s)")
