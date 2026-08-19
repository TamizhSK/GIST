"""yeet run — the whole pipeline. Validates first; refuses on any error.

Wiring only. Every decision worth testing lives in `executor/runner.py`; this
file turns CLI flags into a `RunOptions` and turns a `RunResult` into an exit
code.

This command used to wrap each of its five stages in a `_stage()` helper that
caught `NotImplementedError` and named the owner who still owed us the module.
All five have landed, so the wrappers are gone: a `NotImplementedError` from a
finished module is a bug and should look like one, not like an unfinished
hand-off. The same goes for `EchoSink` (superseded by `RunConsole`) and
`EXIT_NOT_READY` (which shared the value 1 with `EXIT_JOB_FAILED`).

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from yeet.cli import EXIT_BAD_WORKFLOW, EXIT_NO_DOCKER, color_enabled
from yeet.core import gitcreds
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.events import FanOut
from yeet.core.ir import Workflow
from yeet.core.masking import Masker
from yeet.core.project import Project
from yeet.core.result import RunResult
from yeet.executor.backend import Backend, DockerUnavailable
from yeet.executor.docker_backend import DockerBackend
from yeet.executor.images import ImageKind, ImageResolutionError, resolve_image
from yeet.executor.local_backend import LocalBackend
from yeet.executor.runner import RunOptions, run_plan
from yeet.executor.uses import CHECKOUT, bare_name
from yeet.executor.workspace import create
from yeet.expressions.contexts import Contexts, build_github_context
from yeet.planner.plan import ExecutionPlan, build_plan
from yeet.reporting.live import make_console
from yeet.storage.builtin import run_builtin
from yeet.storage.runs import RunStore
from yeet.validation.layer3_semantic import referenced_names
from yeet.validation.pipeline import validate_file


def run(
    ctx: typer.Context,
    flow: Annotated[str | None, typer.Argument(help="Flow name. Default: all discovered.")] = None,
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path(),
    job: Annotated[str | None, typer.Option("--job", help="Run one job only.")] = None,
    event: Annotated[str, typer.Option("--event", help="Simulate a trigger.")] = "push",
    jobs: Annotated[int | None, typer.Option("--jobs", help="Max parallel jobs.")] = None,
    secret: Annotated[
        list[str] | None, typer.Option("--secret", help="K=V, highest precedence.")
    ] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
    tui: Annotated[
        bool,
        typer.Option("--tui", help="Full-screen dashboard instead of streaming output."),
    ] = False,
    clean: Annotated[
        bool,
        typer.Option("--clean", help="Empty workspace; `actions/checkout` fills it, as on GitHub."),
    ] = False,
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Never fetch an action; use the cache only."),
    ] = False,
) -> None:
    """Analyze -> validate -> plan -> execute -> report.

    Layers 0-3 run and HARD STOP on any error before a container is created
    (exit 2). Layer 4 runs and prints but never blocks. That gate is the whole
    reason this tool is safe to point at a repo you did not write.
    """
    root = path.resolve()

    project = _analyze(root)
    target = _pick_flow(project, flow)

    bag, workflow = validate_file(target, upto=4)
    _gate(bag, target, verbose=verbose)
    if workflow is None:
        raise typer.Exit(EXIT_BAD_WORKFLOW)

    # Secrets are resolved BEFORE the contexts are built, because they are one
    # of the contexts. `--secret K=V` wins over the store, which wins over
    # `.env` — `load_secrets` owns that precedence.
    pool = _load_secrets(root, _parse_secrets(secret or []))

    # A container has none of this machine's git credentials, so anything in
    # the workflow that talks to github.com by hand — `git clone`, `git fetch`,
    # `pip install git+https://…` — fails in there while working on the host.
    # Resolved BEFORE the gate so `${{ secrets.GITHUB_TOKEN }}` is a name that
    # exists, and folded into the pool so it is masked like any other secret.
    # See `core/gitcreds.py`.
    token = _github_token(pool)
    if token:
        pool.setdefault("GITHUB_TOKEN", token.token)
        if verbose:
            typer.secho(
                f"github.com credentials: {token.source}", fg=typer.colors.BRIGHT_BLACK, err=True
            )

    # E307 — the one Layer 3 rule that needs data Layer 3 cannot reach. The
    # store is tier 5 and validation is tier 3, so the rule lives there as a
    # pure function and the names are handed to it from here. Gated like the
    # rest of layer 3: a workflow that reads a secret nobody set fails at the
    # step that uses it, minutes in, with an empty string and no explanation.
    _gate(_secret_bag(workflow, set(pool)), target)

    # `.env` and the store are ONE pool of values; the workflow decides which
    # of them are secrets and which are variables, because that is the only
    # place the distinction is written down. It matters twice over: only the
    # secret half is masked (masking `vars.NODE_ENV=production` would replace
    # every "production" in the log with `***`), and only the secret half is
    # gated by E307.
    secret_names = referenced_names(workflow, "secrets")
    var_names = referenced_names(workflow, "vars")
    variables = {k: v for k, v in pool.items() if k in var_names and k not in secret_names}
    secrets = {k: v for k, v in pool.items() if k not in variables}

    masker = Masker()
    masker.update(secrets[k] for k in secret_names if k in secrets)
    # Explicitly, and not through `secret_names`: a token we injected is one
    # the workflow never asked for by name, so nothing above would mask it —
    # and it is about to be handed to every container in the run.
    if token:
        masker.add(token.token)

    contexts = _contexts(root, event, secrets, variables)
    plan = build_plan(workflow, contexts)
    if job is not None:
        plan = _only(plan, job)
    if verbose:
        _echo_plan(plan)

    # The layout is created here rather than inside `run_plan` because its
    # run_id is what names this run's log directory, and the sink needs that
    # id before the first event is emitted.
    layout = create(root)

    if not clean:
        _warn_no_checkout(workflow)

    backend = _backend(root, project, workflow)
    _preflight_docker(backend, project, workflow)
    # `make_console` picks the live tree for a real terminal, plain lines
    # otherwise. Either way it sits beside `RunStore` in a `FanOut`, which is
    # what makes `.yeet/runs/` non-empty and `yeet logs` able to answer —
    # both halves of that were written independently and only wired together
    # here. A failing sink is counted, not raised: a full disk should cost the
    # log file, not the run.
    console_sink = _console_for(
        tui, workflow.display_name, color=color_enabled(ctx), verbose=verbose
    )
    options = RunOptions(
        root=root,
        workflow_name=workflow.display_name,
        event=event,
        max_workers=jobs or os.cpu_count(),
        # Below the workflow's own `env:` (see `runner._job_env`), so a file
        # that sets `GITHUB_TOKEN` to something else still wins.
        env={"GITHUB_TOKEN": token.token} if token else {},
        workflow_env=dict(workflow.env),
        masker=masker,
        # The one place that knows both halves: `storage` implements the
        # built-in actions, the executor runs them, and the tier contract keeps
        # those two from importing each other. See `core/builtins.py`.
        builtins=run_builtin,
        isolated=clean,
        # `YEET_OFFLINE` as well as the flag: a CI image or an air-gapped box
        # wants this on for every run without editing anybody's command line.
        offline=offline or _env_flag("YEET_OFFLINE"),
        sink=FanOut(sinks=[console_sink, RunStore(layout.root, layout.run_id)]),
        contexts=contexts,
        layout=layout,
    )

    # `console_sink` owns a `rich.live.Live` region on a real terminal (a
    # no-op start/stop on a plain pipe) — it has to be open for the whole run
    # so events streaming in from the runner's thread pool land in it, and
    # closed before anything else touches the terminal, success or not.
    console_sink.start()
    try:
        result = _execute(console_sink, plan, backend, options)
    except DockerUnavailable as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_NO_DOCKER) from exc
    finally:
        console_sink.stop()

    console_sink.render_summary(
        result.workflow_name,
        result.status.value,
        result.duration_s,
        run_id=result.run_id,
        job_count=len(result.jobs),
    )
    raise typer.Exit(result.exit_code)


def _env_flag(name: str) -> bool:
    """`YEET_OFFLINE=1`. Set-but-empty is not set — an exported empty variable
    is how a shell script says "no", not "yes"."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _warn_no_checkout(workflow: Workflow) -> None:
    """Say when a run is only working because of the bind mount.

    On GitHub a job starts with an EMPTY workspace, so a workflow with no
    `actions/checkout` anywhere cannot see a single file of the repository and
    fails on its first real command. Here the working tree is mounted, so the
    same workflow passes — and passes for a reason that will not exist in CI.

    Once per run, and only in the default mode: `--clean` reproduces GitHub's
    empty workspace, where this stops being a warning and becomes the failure
    it already is upstream. Not a lint (layer 4) on purpose — a job that only
    downloads an artifact and deploys it needs no checkout, and static analysis
    cannot tell that job from a broken one. What CAN be said precisely is that
    the whole workflow has none, which is nearly always an oversight.
    """
    for job in workflow.jobs.values():
        for step in job.steps:
            if step.uses and bare_name(step.uses) == CHECKOUT:
                return
    if not any(job.steps for job in workflow.jobs.values()):
        return
    typer.secho(
        "[!] no `actions/checkout` step in this workflow. It works here because your "
        "working tree is mounted; on GitHub the workspace starts empty. "
        "Try `yeet run --clean` to run it the way GitHub would.",
        fg=typer.colors.YELLOW,
        err=True,
    )


# --- stages ------------------------------------------------------------------


def _execute(sink: Any, plan: ExecutionPlan, backend: Backend, options: RunOptions) -> RunResult:
    """Run the plan, giving Textual the main thread when it is the renderer.

    Textual installs signal handlers and so must own the main thread; the RUN
    is what moves to a worker. Everything else — including the backend, which
    registers the SIGINT container reaping — was built on the main thread
    above and stays there.
    """
    from yeet.reporting.dashboard import DashboardSink, run_dashboard

    if isinstance(sink, DashboardSink):
        return run_dashboard(sink, lambda: run_plan(plan, backend, options))
    return run_plan(plan, backend, options)


def _console_for(tui: bool, workflow_name: str, *, color: bool, verbose: bool) -> Any:
    """The dashboard when asked for and possible, the streaming pair otherwise.

    `--tui` is a nicety and Textual is an OPTIONAL dependency, so a missing
    install degrades to the normal renderer with one line saying why — a runner
    that refuses to run because a display library is absent has failed at its
    actual job. The same fallback covers a pipe: a full-screen app writing to
    something that is not a terminal produces nothing a person can read.
    """
    if not tui:
        return make_console(color=color, verbose=verbose)

    from yeet.reporting import dashboard

    if not dashboard.is_available():
        typer.secho(
            "--tui needs Textual: pip install textual. Using the streaming view.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return make_console(color=color, verbose=verbose)
    if not sys.stdout.isatty():
        typer.secho(
            "--tui needs a terminal; this is a pipe. Using the streaming view.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return make_console(color=color, verbose=verbose)
    return dashboard.DashboardSink(workflow_name=workflow_name, color=color)


def _analyze(root: Path) -> Project:
    from yeet.analyzer.project import analyze

    return analyze(root)


def _secret_bag(workflow: Workflow, available: set[str]) -> DiagnosticBag:
    from yeet.validation.layer3_semantic import check_secrets

    bag = DiagnosticBag()
    bag.extend(check_secrets(workflow, available))
    return bag


def _github_token(pool: dict[str, str]) -> gitcreds.Credential:
    """A token for github.com — the project's own first, the machine's second.

    The project wins because it is the explicit answer: someone who ran
    `yeet secrets set GITHUB_TOKEN` in this repository meant THAT token for
    THIS repository, and silently preferring whatever `gh` happens to be logged
    in as would run their workflow as the wrong account.

    Only then does `gitcreds.discover_token()` go looking at the machine, which
    is the case that needs no setup at all: a developer who has ever run
    `gh auth login` or cloned a private repo over HTTPS already has one.
    """
    for name in gitcreds.TOKEN_ENV_NAMES:
        value = pool.get(name, "").strip()
        if value:
            return gitcreds.Credential(value, f"`{name}` from .yeet/.secrets or .env")
    return gitcreds.discover_token()


def _load_secrets(root: Path, overrides: dict[str, str]) -> dict[str, str]:
    """Everything `secrets/store.py` can find, plus `--secret` on top.

    A locked store is not fatal: most workflows need no secrets, and refusing
    to run because a passphrase is absent would make the encryption everyone's
    problem rather than only the problem of people who use it. It is said out
    loud, though — a run that silently masked nothing would be worse than
    either. `--secret` values still apply in that case.
    """
    from yeet.secrets.store import SecretsError, SecretsLocked, load_secrets

    try:
        return load_secrets(root, overrides)
    except SecretsLocked as exc:
        typer.secho(
            f"{exc} Running with --secret values and .env only.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    except SecretsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
    return dict(overrides)


def _contexts(
    root: Path, event: str, secrets: dict[str, str], variables: dict[str, str]
) -> Contexts:
    """The RUN-WIDE contexts for `${{ }}` — the ones that cannot vary per job.

    `secrets` is passed in rather than left empty: `Contexts` has had the field
    since B5, but nothing populated it, so `${{ secrets.NPM_TOKEN }}` evaluated
    to nothing and a step's `drip:`/`env:` got an empty string. The values were
    reaching the `Masker` (so nothing leaked) and never reaching the workflow —
    which looks exactly like a masking success until you check the exit code of
    the thing that needed the token.

    That was one of six fields with the same disease. `matrix`, `needs`, `job`,
    `env`, `steps` and `runner` all vary per job instance or per step, so they
    cannot be filled here and are filled by `executor/contexts.py` instead —
    `for_instance` in the runner, `for_step` in the step loop. What is built
    here is only what is true for the whole run.
    """
    contexts = Contexts(env=dict(os.environ))
    contexts.root = root
    contexts.github = dict(build_github_context(root, event))
    contexts.secrets = dict(secrets)
    contexts.vars = dict(variables)
    return contexts


def _backend(root: Path, project: Project, workflow: Workflow) -> Backend:
    """Docker unless every job asked for `cooked_on: local`.

    Deciding once, up front, means a project that cannot reach a daemon but
    only runs local jobs never touches the SDK at all.
    """
    kinds, _ = _image_kinds(project, workflow)
    if kinds and kinds <= {ImageKind.LOCAL}:
        return LocalBackend(root)
    return DockerBackend(root, project=project)


def _image_kinds(project: Project, workflow: Workflow) -> tuple[set[ImageKind], bool]:
    """Which kinds of image this workflow wants, and whether any is unknowable.

    The second half of the tuple is `runs-on: ${{ matrix.os }}` — the matrix has
    not been expanded here and there is no leg to ask, so the value genuinely
    cannot be resolved yet. It is not LOCAL either, so the backend assumes a
    container and re-resolves per leg, where the value is finally known.
    """
    kinds: set[ImageKind] = set()
    unknowable = False
    for job in workflow.jobs.values():
        if job.runs_on and "${{" in job.runs_on:
            kinds.add(ImageKind.BASE)
            unknowable = True
            continue
        try:
            kinds.add(resolve_image(job, project).kind)
        except ImageResolutionError:
            kinds.add(ImageKind.BASE)
    return kinds, unknowable


def _preflight_docker(backend: Backend, project: Project, workflow: Workflow) -> None:
    """Reach the daemon ONCE, before the run starts, or exit 3 saying why.

    Three things go wrong without this, and all three are the first experience
    of a user whose Docker is not running:

    * the connection is attempted from inside the thread pool, once per job, so
      a five-job workflow prints the same "no daemon" error five times,
    * it is attempted AFTER the live console has taken over the terminal, so
      the error lands in the middle of a half-drawn run tree,
    * every one of those attempts pays its own connect timeout, in parallel,
      for an answer that was the same before the first one started.

    Skipped when any job's `runs-on` is still an expression: that workflow may
    turn out to be entirely `cooked_on: local`, and refusing to start it over a
    daemon it will never touch would be a regression. Those legs keep the
    existing per-job path, which reaches the same exit code by a slower road.
    """
    if not isinstance(backend, DockerBackend):
        return
    kinds, unknowable = _image_kinds(project, workflow)
    if unknowable or not (kinds - {ImageKind.LOCAL}):
        return
    try:
        backend.client  # noqa: B018 - the property IS the connection, and it caches
    except DockerUnavailable as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_NO_DOCKER) from exc


def _echo_plan(plan: ExecutionPlan) -> None:
    """`-v`: what we are about to do, before we do it."""
    total = sum(len(wave) for wave in plan.waves)
    typer.echo(f"plan: {total} job instance(s) in {len(plan.waves)} wave(s)", err=True)
    for number, wave in enumerate(plan.waves, start=1):
        typer.echo(f"  wave {number}: {', '.join(inst.key for inst in wave)}", err=True)


# --- helpers -----------------------------------------------------------------


def _pick_flow(project: Project, flow: str | None) -> Path:
    if not project.flows:
        typer.secho(
            "No flows found. Try `yeet init --auto` to generate one.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(EXIT_BAD_WORKFLOW)
    if flow is None:
        return project.flows[0]
    for candidate in project.flows:
        if flow in (candidate.name, candidate.stem):
            return candidate
    typer.secho(f"No flow named `{flow}`.", fg=typer.colors.RED, err=True)
    raise typer.Exit(EXIT_BAD_WORKFLOW)


def _gate(bag: DiagnosticBag, source: Path, *, verbose: bool = False) -> None:
    """The gate. Errors stop the run BEFORE any container exists.

    ERRORS are rendered in full, with their code frames: the run is about to
    stop and the frame is the whole reason the user can fix it in one pass.

    WARNINGS ARE COUNTED, NOT PRINTED. `yeet run` is the command you type to
    watch your build; it is not the command you type to read a lint report, and
    `yeet check` already exists and prints every one of them with context. A
    screenful of layer 4 before every single run buries the thing the user
    actually asked for — and a report you scroll past on the way to the output
    you wanted is a report nobody reads. `-v` prints them here for the case
    where you do want both at once.

    Layer 4 still RUNS, and still never blocks. Only where it is displayed
    changed.
    """
    from yeet.reporting.render import render_diagnostics

    if bag.has_errors():
        typer.echo(render_diagnostics(bag), err=True)
        typer.secho(
            f"{len(bag.errors)} error(s) in {source} — refusing to run.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(EXIT_BAD_WORKFLOW)

    if not bag.warnings:
        return
    if verbose:
        typer.echo(render_diagnostics(bag), err=True)
        return
    codes = ", ".join(sorted({d.code for d in bag.warnings}))
    typer.secho(
        f"[!] {len(bag.warnings)} warning(s) ({codes}) — `yeet check` shows them, `-v` here.",
        fg=typer.colors.YELLOW,
        err=True,
    )


def _only(plan: ExecutionPlan, job: str) -> ExecutionPlan:
    """`--job build` — keep that job's instances and drop the rest."""
    waves = [[inst for inst in wave if job in (inst.key, inst.job.key)] for wave in plan.waves]
    return ExecutionPlan(waves=[wave for wave in waves if wave])


def _parse_secrets(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if sep and key.strip():
            out[key.strip()] = value
    return out
