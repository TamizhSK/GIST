"""GitHub-Actions-style live tree: jobs and steps drawn as ASCII-art branches
(`+--`, `\\--`, `|`, the same four glyphs `tree --charset ascii` uses), kept
in place with `rich.live.Live`, spinner-to-checkmark per step, timing on
completion.

ASCII throughout on purpose, not Unicode box-drawing or Braille spinner
frames: this has to look right on a legacy Windows console codepage as much
as a UTF-8 terminal, in the same spirit as an oh-my-zsh theme built for
portability over Powerline glyphs.

Self-contained: this module is the only place that talks to `rich.live`.
`reporting.console.RunConsole` — the plain, line-at-a-time renderer — is
unaffected and stays what a piped/redirected run gets, because `Live`'s
repaint is cursor-control codes and those corrupt a file or a pipe.
`make_console()` is the one entry point `cmd_run` needs: it picks whichever
of the two a real terminal deserves.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Protocol, TextIO

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.live import Live
from rich.text import Text

from yeet.core.events import (
    JOB_END,
    JOB_START,
    META,
    STDERR,
    STEP_END,
    STEP_START,
    LogEvent,
)
from yeet.core.result import Status
from yeet.reporting.console import RunConsole
from yeet.reporting.theme import (
    BLANK,
    BRANCH,
    LAST_BRANCH,
    PIPE,
    SYMBOL_FAIL,
    SYMBOL_PASS,
    SYMBOL_SKIP,
    format_summary,
)

REFRESH_HZ = 8
SPINNER_FRAMES = "-\\|/"
SPINNER_INTERVAL_S = 0.1
"""The classic four-frame ASCII spinner — `-\\|/` — not one of rich's Braille
`dots` frames: those are Unicode and a legacy Windows console codepage
(cp1252, cp437, ...) cannot encode them, which is a crash waiting to happen
on exactly the platform most likely to lack a real terminal already."""
LIVE_TAIL_LINES = 20
"""How many stdout/stderr lines a still-running, non-verbose step shows. GH
Actions streams the tail of a running step's log too — the point of "live" is
watching the last thing that happened, not the first."""
MAX_STORED_LINES = 5000
"""A hard cap per node so a chatty step (or a runaway one) cannot turn the
live tree into an unbounded buffer. `--verbose` on a step with more output
than this sees a truncated tail, not a crash."""

_GLYPHS: dict[str, tuple[str, str]] = {
    Status.SUCCESS.value: (SYMBOL_PASS, "bold green"),
    Status.FAILURE.value: (SYMBOL_FAIL, "bold red"),
    Status.SKIPPED.value: (SYMBOL_SKIP, "dim"),
    Status.CANCELLED.value: (SYMBOL_SKIP, "dim"),
}
"""Same glyphs `theme.py` gives the plain console — a run must look like the
same tool whether or not it happened to be piped."""

_STDOUT_STYLE = "grey58"
_STDERR_STYLE = "red"
_META_STYLE = "grey50 italic"


def _line_style(stream: str) -> str:
    if stream == STDERR:
        return _STDERR_STYLE
    if stream == META:
        return _META_STYLE
    return _STDOUT_STYLE


class ConsoleSink(Protocol):
    """What `cmd_run` needs from whichever renderer `make_console` returns."""

    def emit(self, event: LogEvent) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def render_summary(
        self,
        workflow_name: str,
        status: str,
        duration_s: float,
        *,
        run_id: str = ...,
        job_count: int = ...,
    ) -> None: ...


def is_live_capable(stream: TextIO | None = None) -> bool:
    """False for a pipe, a redirect, or a file — anywhere `Live`'s cursor
    movement would come out as literal escape-code garbage instead of an
    in-place repaint."""
    stream = stream if stream is not None else sys.stdout
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def make_console(
    out: TextIO | None = None, *, color: bool = True, verbose: bool = False
) -> ConsoleSink:
    """The one thing `cmd_run` calls. A real terminal gets the live tree; a
    pipe, redirect, or CI log gets `RunConsole`'s plain lines — same event
    stream, same status vocabulary, different renderer for the same reason
    `ls` behaves differently piped to `less` than printed to a tty.
    """
    stream = out if out is not None else sys.stdout
    if is_live_capable(stream):
        return LiveRunConsole(stream, color=color, verbose=verbose)
    return RunConsole(stream, color=color, verbose=verbose)


class _SpinnerLine:
    """One line: `<prefix><frame> <name>`, `frame` picked from wall-clock time
    inside `__rich_console__` — the same trick `rich.spinner.Spinner` uses to
    animate under `Live`'s own refresh thread even between our `emit()`
    calls, just computing an ASCII frame instead of a Unicode one and baking
    the tree's branch prefix into the same line rather than needing a second
    renderable next to it.

    One instance is cached per running node and reused across renders (see
    `LiveRunConsole._label`) — a fresh instance every frame would still show
    *a* spinner, but always frame zero, which is not a spinner.
    """

    def __init__(self, prefix: str, name: str, style: str) -> None:
        self.prefix = prefix
        self.name = name
        self.style = style

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        frame = SPINNER_FRAMES[int(time.monotonic() / SPINNER_INTERVAL_S) % len(SPINNER_FRAMES)]
        yield Text(f"{self.prefix}{frame} {self.name}", style=self.style)


class _StepNode:
    __slots__ = ("name", "status", "duration_s", "lines", "spinner")

    def __init__(self, name: str) -> None:
        self.name = name
        self.status = Status.RUNNING.value
        self.duration_s: float | None = None
        self.lines: list[tuple[str, str]] = []
        self.spinner: _SpinnerLine | None = None


class _JobNode:
    __slots__ = ("name", "status", "duration_s", "steps", "order", "lines", "spinner")

    def __init__(self, name: str) -> None:
        self.name = name
        self.status = Status.RUNNING.value
        self.duration_s: float | None = None
        self.steps: dict[str, _StepNode] = {}
        self.order: list[str] = []
        self.lines: list[tuple[str, str]] = []
        self.spinner: _SpinnerLine | None = None


class LiveRunConsole:
    """Implements `core.events.LogSink`. Renders every job as an ASCII-art
    branch list, all of them held in place by one `Live` region, redrawn as
    events stream in.

    Jobs run in parallel (the runner's `ThreadPoolExecutor`), so `emit()` is
    called from several threads at once — every mutation of the tree state
    happens under `self._lock`, `Live.update()` included, so two legs of a
    matrix finishing in the same instant cannot tear the tree.

    Construction never touches the terminal: `start()` opens the live region,
    `stop()` closes it and leaves the finished tree in scrollback (the run's
    permanent record), and `cmd_run` is what decides when each happens.
    """

    def __init__(
        self, out: TextIO | None = None, *, color: bool = True, verbose: bool = False
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self._color = color
        self.verbose = verbose
        self._console = Console(
            file=self.out,
            color_system="auto" if color else None,
            highlight=False,
            soft_wrap=True,
        )
        self._live = Live(console=self._console, refresh_per_second=REFRESH_HZ, transient=False)
        self._jobs: dict[str, _JobNode] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def __enter__(self) -> LiveRunConsole:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        self._live.start()

    def stop(self) -> None:
        self._live.stop()

    # -- LogSink -------------------------------------------------------------

    def emit(self, event: LogEvent) -> None:
        with self._lock:
            job = self._jobs.get(event.job)
            if job is None:
                job = _JobNode(event.job)
                self._jobs[event.job] = job
                self._order.append(event.job)

            if event.kind == JOB_START:
                job.status = Status.RUNNING.value
            elif event.kind == JOB_END:
                job.status = event.status or job.status
                job.duration_s = event.duration_s
                job.spinner = None
            elif event.kind == STEP_START:
                self._step(job, event.step).status = Status.RUNNING.value
            elif event.kind == STEP_END:
                step = self._step(job, event.step)
                step.status = event.status or step.status
                step.duration_s = event.duration_s
                step.spinner = None
            else:
                self._append_line(job, event)

            self._live.update(self._render())

    def _step(self, job: _JobNode, name: str) -> _StepNode:
        step = job.steps.get(name)
        if step is None:
            step = _StepNode(name)
            job.steps[name] = step
            job.order.append(name)
        return step

    def _append_line(self, job: _JobNode, event: LogEvent) -> None:
        text = event.text.rstrip("\r\n")
        if not text or text.startswith("::group::") or text == "::endgroup::":
            # The tree's own nesting is the grouping; GH-style `::group::`
            # markers exist for a scrollback log, not a live redraw.
            return
        target = self._step(job, event.step).lines if event.step else job.lines
        target.append((event.stream, text))
        del target[:-MAX_STORED_LINES]

    # -- rendering -------------------------------------------------------------

    def _render(self) -> RenderableType:
        if not self._order:
            return Text("waiting for the first job to start...", style="dim")
        parts: list[RenderableType] = []
        for index, job_name in enumerate(self._order):
            if index:
                parts.append(Text(""))
            parts.extend(self._job_lines(self._jobs[job_name]))
        return Group(*parts)

    def _job_lines(self, job: _JobNode) -> list[RenderableType]:
        """One job, flattened to a list of already-indented lines — ASCII-art
        branches (`BRANCH`/`LAST_BRANCH`) baked into the text of each line
        rather than drawn by a tree widget, so the same four glyphs
        `reporting.console` uses stay the only tree-drawing vocabulary in
        the codebase.
        """
        lines: list[RenderableType] = [self._label("", job.name, job.status, job.duration_s, job)]

        for stream, text in job.lines:
            lines.append(Text(f"{BLANK}{text}", style=_line_style(stream)))

        last_index = len(job.order) - 1
        for index, step_name in enumerate(job.order):
            step = job.steps[step_name]
            is_last = index == last_index
            branch = LAST_BRANCH if is_last else BRANCH
            continuation = BLANK if is_last else PIPE

            lines.append(self._label(branch, step.name, step.status, step.duration_s, step))
            for stream, text in self._visible_lines(step):
                style = _line_style(stream)
                lines.append(Text(f"{continuation}{BLANK}{text}", style=style))

        return lines

    def _label(
        self,
        prefix: str,
        name: str,
        status: str,
        duration_s: float | None,
        node: _JobNode | _StepNode,
    ) -> RenderableType:
        if status == Status.RUNNING.value:
            if node.spinner is None:
                node.spinner = _SpinnerLine(prefix, name, style="bold yellow")
            return node.spinner
        icon, style = _GLYPHS.get(status, ("[?]", "white"))
        suffix = f" ({_fmt_duration(duration_s)})" if duration_s is not None else ""
        return Text(f"{prefix}{icon} {name}{suffix}", style=style)

    def _visible_lines(self, step: _StepNode) -> list[tuple[str, str]]:
        """META notes (skip/timeout/degraded reasons) always show — they are
        never raw output. stdout/stderr is tailed, in full for a step that
        failed (you came here to see why) or when `--verbose` asked for it.

        A finished step keeps its tail rather than dropping to META-only. GH
        Actions can collapse a green step to nothing because the log is one
        click away; the equivalent here is `yeet logs`, which is two commands
        and a run id away, and in between the user is looking at a build that
        printed no evidence it did anything. `echo` is how people debug these
        files — a runner whose default output contains none of it reads as
        broken even when it is not.
        """
        if self.verbose or step.status == Status.FAILURE.value:
            return step.lines
        kept: list[tuple[str, str]] = []
        body_budget = LIVE_TAIL_LINES
        for stream, text in reversed(step.lines):
            if stream == META:
                kept.append((stream, text))
            elif body_budget > 0:
                kept.append((stream, text))
                body_budget -= 1
        kept.reverse()
        return kept

    # -- summary ---------------------------------------------------------------

    def render_summary(
        self,
        workflow_name: str,
        status: str,
        duration_s: float,
        *,
        run_id: str = "",
        job_count: int = 0,
    ) -> None:
        """Written directly to `self.out`, not through the `rich.Console` used
        for the live region: `format_summary` already returns ANSI-coded
        text (the same string `RunConsole` prints), and handing pre-coded
        ANSI through `Console.print` risks it being re-escaped or re-wrapped.
        One format function, one way of writing it out, for both renderers.
        """
        summary = format_summary(
            workflow_name, status, duration_s, run_id=run_id, job_count=job_count, color=self._color
        )
        try:
            self.out.write(summary + "\n")
            self.out.flush()
        except Exception:
            pass


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"
