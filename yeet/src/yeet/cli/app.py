"""Typer app. Wires subcommands. Owns exit codes: 0 ok, 1 job failed, 2 bad file, 3 no docker.

SHARED FILE. One line per subcommand registration, at the end of the block.
Add your line, do not reformat the file — see plan.md 8.

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import contextlib
import io
import sys

import typer

from yeet import __version__
from yeet.cli import (
    cmd_check,
    cmd_explain,
    cmd_graph,
    cmd_hooks,
    cmd_init,
    cmd_logs,
    cmd_prune,
    cmd_run,
    cmd_scan,
    cmd_secrets,
    cmd_watch,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="A local, GitHub Actions-compatible workflow runner — with a dialect of its own.",
)

# --- subcommand registrations: one line each, append at the end --------------
app.command("scan")(cmd_scan.scan)
app.command("check")(cmd_check.check)
app.command("explain")(cmd_explain.explain)
app.command("init")(cmd_init.init)
app.command("run")(cmd_run.run)
app.command("graph")(cmd_graph.graph)
app.command("logs")(cmd_logs.logs)
app.command("watch")(cmd_watch.watch)
app.command("prune")(cmd_prune.prune)
app.add_typer(cmd_hooks.hooks_app, name="hooks")
app.add_typer(cmd_secrets.secrets_app, name="secrets")
# ----------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
    no_color: bool = typer.Option(
        False, "--no-color", help="Disable colored output. NO_COLOR is honored too."
    ),
) -> None:
    if version:
        typer.echo(f"yeet {__version__}")
        raise typer.Exit(0)
    ctx.obj = {"no_color": no_color}


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError):
                stream.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
