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
from yeet.executor.docker_backend import reap_project
from yeet.executor.workspace import prune_tmp


def prune(
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    images: Annotated[
        bool, typer.Option("--images/--no-images", help="Remove built images.")
    ] = True,
    all_projects: Annotated[
        bool,
        typer.Option("--all", help="Every project's images, not just this one's."),
    ] = False,
) -> None:
    """Remove this project's images, its leftover containers, and `.yeet/tmp/`.

    Scoped to the project by default. `yeet-local/*` images and `yeet-*`
    containers carry a project slug derived from the absolute path, so pruning
    here cannot delete the image another checkout is about to use — or stop a
    container a run in another terminal is still writing to. `--all` sweeps
    everything this tool has ever built on the machine.

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

    # Containers first: an image cannot be removed while a container built from
    # it still exists, so pruning images before containers silently does
    # nothing on exactly the machines that need it most.
    stale = reap_project(client, root)
    for name in stale:
        typer.echo(f"  removed container {name}")

    removed = prune_images(client, None if all_projects else root)
    for tag in removed:
        typer.echo(f"  removed {tag}")
    typer.echo(f"removed {len(stale)} container(s) and {len(removed)} image(s)")
