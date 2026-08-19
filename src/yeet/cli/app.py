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
    cmd_doctor,
    cmd_explain,
    cmd_graph,
    cmd_hooks,
    cmd_init,
    cmd_logs,
    cmd_prune,
    cmd_run,
    cmd_scan,
    cmd_secrets,
    cmd_upgrade,
    cmd_watch,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    # ASCII, like every other string this prints. `--help` is the first thing
    # a Windows user runs and cp437 has no em dash.
    help="A local, GitHub Actions-compatible workflow runner - with a dialect of its own.",
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
app.command("doctor")(cmd_doctor.doctor)
app.command("upgrade")(cmd_upgrade.upgrade)
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
        for line in _version_lines():
            typer.echo(line)
        raise typer.Exit(0)
    ctx.obj = {"no_color": no_color}


def _version_lines() -> list[str]:
    """Version, interpreter, OS, and whether Docker answered.

    Four lines rather than one because this is what gets pasted into an issue,
    and the three follow-up questions were always the same three.
    """
    import platform

    from yeet.executor.platform_ import is_wsl, runner_arch

    system = f"{platform.system()} {platform.release()} ({runner_arch()})"
    if is_wsl():
        system += " [WSL]"
    return [
        f"yeet {__version__}",
        f"python {platform.python_version()} ({sys.executable})",
        f"os     {system}",
        f"docker {_docker_line()}",
    ]


def _docker_line() -> str:
    """Reachable or not, in one line. Never raises and never takes long —
    `--version` is also what a script calls to check the tool is installed."""
    try:
        from yeet.executor.backend import DockerUnavailable, get_docker_client

        client = get_docker_client()
        return str(client.version().get("Version", "reachable"))
    except DockerUnavailable as exc:
        return f"not available ({exc})"
    except Exception:  # noqa: BLE001 - a version banner must never fail
        return "not available"


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError):
                stream.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
