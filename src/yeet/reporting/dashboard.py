"""`yeet run --tui`: a full-screen dashboard for watching a run.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md

WHY THIS IS OPT-IN AND NOT THE DEFAULT. Textual draws into the terminal's
ALTERNATE SCREEN — the same buffer `less` and `vim` use — and the alternate
screen is discarded on exit. That is exactly right for an app you are looking
at and exactly wrong for a build log you want to read afterwards, pipe into
`grep`, or find in a CI transcript. `reporting.live` (a rich `Live` region that
leaves its output in the scrollback) and `reporting.console` (one `write()` per
line) remain the default pair. This is the third renderer, for the case where
you are WATCHING rather than reading: a matrix with eight legs, where the
streaming form interleaves eight jobs into one column and the thing you want is
to click on one.

It is a `core.events.LogSink` like the other two, so it needs no special
plumbing — `cmd_run` puts it in the same `FanOut` beside `RunStore`, and the
run is recorded to disk identically whichever renderer is on screen. If the
dashboard is killed, the JSONL is still complete and `yeet logs` still replays
it.

THREAD SAFETY. `emit` is called from the runner's worker threads, one per job,
while Textual's event loop runs on the main thread. Every mutation of the
widget tree therefore goes through `call_from_thread`, which is the only
supported way in; touching a widget directly from a worker is a race that
shows up as a corrupted screen an hour later.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from yeet.core.events import (
    JOB_END,
    JOB_START,
    META,
    STDERR,
    STEP_END,
    STEP_START,
    LogEvent,
)
from yeet.reporting.theme import (
    STATUS_FLOPPED,
    STATUS_SLAYED,
    SYMBOL_FAIL,
    SYMBOL_PASS,
    SYMBOL_RUNNING,
    SYMBOL_SKIP,
    sunset,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from textual.app import ComposeResult

try:  # `Text` is used by `_label`, which is module-level
    from rich.text import Text
except ImportError:  # pragma: no cover - rich is a hard dependency
    Text = None  # type: ignore[assignment,misc]

T = TypeVar("T")

MAX_LINES_PER_STEP = 2000
"""A chatty step must not turn the pane into an unbounded buffer. The whole log
is on disk in `.yeet/runs/` either way — this is a window, not the record."""

# The wordmark's gradient, sampled where each part of the UI sits in it, read
# from `theme.sunset` rather than copied — so the dashboard, the streaming
# renderers, the installer banner and `assets/yeet.svg` are all tinted from one
# table and cannot drift apart.
#
# The mapping is the same one the logo uses: top of the screen is the top of
# the wordmark (indigo), the middle is its magenta, and whatever is RUNNING is
# the lit sun at its baseline. The eye finds the live row without reading it.
_SKY = sunset(0.00)[1]  # indigo — the top of the letters
_JOB = sunset(0.10)[1]  # a job header
_STEP = sunset(0.44)[1]  # magenta — the middle of the word
_WARM = sunset(0.70)[1]  # rose, between magenta and the sun
_SUN = sunset(0.98)[1]  # the lit sun — whatever is happening now
_DEEP = sunset(0.00)[2]  # the deepest indigo: rules and chrome
_EMBER = sunset(0.86)[2]  # the sun's shadow: the status bar's ground
_OK = "#87d787"
_BAD = "#ff5f5f"  # the sun's shadow: the status bar's ground

_BG = "#0b0b12"  # the backdrop the wordmark is drawn on
_BG_LOG = "#0e0e18"  # one step lighter, so the two panes separate without a rule

#: The banner wordmark, one gradient band per letter. Six would be the logo's
#: six rows; here it is one row, so the ramp runs ACROSS instead of down.
_BANNER_BANDS = (0.02, 0.20, 0.38, 0.56, 0.74, 0.92)

CSS = f"""
Screen {{ background: {_BG}; }}

#body {{ height: 1fr; }}

#tree {{
    width: 44;
    background: {_BG};
    border-right: solid {_DEEP};
    padding: 0 1;
    scrollbar-color: {_DEEP};
    scrollbar-color-hover: {_STEP};
    scrollbar-background: {_BG};
}}

/* The tree's own cursor and guides, so a selected job reads as selected
   without a second colour system arriving from Textual's defaults. */
#tree > .tree--guides {{ color: {_DEEP}; }}
#tree > .tree--guides-hover {{ color: {_STEP}; }}
#tree > .tree--guides-selected {{ color: {_SUN}; }}
#tree > .tree--cursor {{ background: {_DEEP}; color: {_SUN}; text-style: bold; }}

#log {{
    background: {_BG_LOG};
    padding: 0 1;
    scrollbar-color: {_DEEP};
    scrollbar-background: {_BG_LOG};
}}

#banner {{
    height: 1;
    background: {_BG};
    padding: 0 1;
}}

#status {{
    height: 1;
    background: {_EMBER};
    color: {_SUN};
    text-style: bold;
    padding: 0 1;
}}
"""


@dataclass
class _Step:
    name: str
    status: str = "running"
    duration_s: float | None = None
    lines: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _Job:
    name: str
    status: str = "running"
    duration_s: float | None = None
    steps: dict[str, _Step] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def is_available() -> bool:
    """Is Textual installed? It is an OPTIONAL dependency.

    `--tui` is a nicety; a runner that cannot start because a display library
    is missing has failed at its actual job. The CLI checks this and falls back
    to the streaming renderer with a line saying why.
    """
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


class DashboardSink:
    """A `LogSink` that feeds a Textual app running on the main thread.

    The queue is the whole design. `emit` is called from N worker threads and
    must never block them — a renderer that stalls the runner has changed the
    thing it was supposed to observe — so it appends and returns, and the app
    drains on a timer.
    """

    def __init__(self, *, workflow_name: str = "", color: bool = True) -> None:
        self.workflow_name = workflow_name
        self.color = color
        self._events: queue.Queue[LogEvent] = queue.Queue()
        self._app: Any = None
        self._thread: threading.Thread | None = None
        self._done = threading.Event()

    # -- LogSink -------------------------------------------------------------

    def emit(self, event: LogEvent) -> None:
        self._events.put(event)

    def start(self) -> None:
        """No-op: `run_dashboard` owns the lifecycle.

        The app CANNOT be started from here, and finding out why is worth
        recording. Textual's driver installs SIGTSTP/SIGWINCH handlers, and
        `signal.signal` raises `ValueError: signal only works in main thread`
        anywhere else — so the obvious layout (app on a worker, `run_plan` on
        the main thread) does not run at all. `run_dashboard` inverts it.
        """

    def stop(self) -> None:
        self._done.set()

    def render_summary(
        self,
        workflow_name: str,
        status: str,
        duration_s: float,
        *,
        run_id: str = "",
        job_count: int = 0,
    ) -> None:
        """The dashboard is gone by now — the alternate screen took the whole
        run with it. The summary is printed by `cmd_run` through the plain
        renderer instead, which is also what lands in the scrollback the user
        is left looking at."""


def run_dashboard(sink: DashboardSink, work: Callable[[], T]) -> T:
    """Run `work` on a worker thread while the dashboard owns the main one.

    Textual must have the main thread (see `DashboardSink.start`), so the RUN
    is what moves. Three consequences, all deliberate:

    * The backend — and therefore `install_cleanup_handlers`, which registers
      SIGINT/SIGTERM container reaping — is constructed by `cmd_run` on the
      main thread BEFORE this is called. Move that and Ctrl-C stops reaping.
    * The app closes itself when `work` returns, so the dashboard is a view of
      one run rather than something the user has to dismiss.
    * `work`'s exception is re-raised HERE, on the main thread, after the app
      has torn the alternate screen down. Raising it inside the worker would
      print a traceback onto a screen that is about to be discarded.
    """
    holder: dict[str, Any] = {}
    app = _YeetApp(sink)
    sink._app = app

    def worker() -> None:
        try:
            holder["value"] = work()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            holder["error"] = exc
        finally:
            # Suppressed because the app may already be gone — the user can
            # press `q` before the run finishes, and asking a dead app to exit
            # must not turn a finished run into a crash.
            with contextlib.suppress(Exception):
                app.call_from_thread(app.exit)

    thread = threading.Thread(target=worker, name="yeet-run")
    thread.start()
    try:
        app.run()
    finally:
        thread.join()

    if "error" in holder:
        raise holder["error"]
    return holder["value"]  # type: ignore[no-any-return]


try:  # pragma: no cover - exercised only where textual is installed
    from rich.text import Text
    from textual.app import App
    from textual.containers import Horizontal
    from textual.widgets import RichLog, Static, Tree

    class _YeetApp(App[None]):
        CSS = CSS
        BINDINGS = [
            ("q", "quit", "quit"),
            ("f", "follow", "follow the running step"),
        ]

        def __init__(self, sink: DashboardSink) -> None:
            super().__init__()
            self._sink = sink
            self._jobs: dict[str, _Job] = {}
            self._order: list[str] = []
            # Named `_tree_nodes`, not `_nodes`: `DOMNode` already defines `_nodes`
            # as its child NodeList, and shadowing it corrupts the widget
            # tree in ways that surface much later than this line.
            self._tree_nodes: dict[tuple[str, str], Any] = {}
            self._selected: tuple[str, str] | None = None
            self._follow = True

        def compose(self) -> ComposeResult:
            yield Static(self._banner(), id="banner")
            with Horizontal(id="body"):
                tree: Tree[str] = Tree("run", id="tree")
                tree.show_root = False
                yield tree
                yield RichLog(id="log", wrap=False, highlight=False, markup=False)
            yield Static("  starting…", id="status")

        def _banner(self) -> Text:
            """`yeet` in the wordmark's gradient, then the workflow name.

            One band per letter rather than one flat colour: it is the same
            ramp the logo runs down its twelve rows, turned on its side to fit
            a one-line header.
            """
            text = Text("  ")
            for index, letter in enumerate("yeet"):
                band = _BANNER_BANDS[min(index, len(_BANNER_BANDS) - 1)]
                text.append(letter, style=f"bold {sunset(band)[1]}")
            text.append("  ·  ", style=_DEEP)
            text.append(self._sink.workflow_name, style=f"bold {_STEP}")
            return text

        def on_mount(self) -> None:
            # 20 Hz: fast enough that a step's output feels live, slow enough
            # that a job printing thousands of lines does not spend the whole
            # run repainting instead of draining.
            self.set_interval(1 / 20, self._drain)

        def action_follow(self) -> None:
            self._follow = not self._follow
            self._set_status()

        def on_tree_node_selected(self, event: Any) -> None:
            key = getattr(event.node, "data", None)
            if isinstance(key, tuple):
                self._selected = key
                self._follow = False
                self._repaint_log()

        # -- draining ---------------------------------------------------------

        def _drain(self) -> None:
            changed = False
            for _ in range(500):  # bounded: never starve the repaint
                try:
                    event = self._sink._events.get_nowait()
                except queue.Empty:
                    break
                self._apply(event)
                changed = True
            if changed:
                self._set_status()

        def _apply(self, event: LogEvent) -> None:
            job = self._jobs.get(event.job)
            if job is None:
                job = _Job(name=event.job)
                self._jobs[event.job] = job
                self._order.append(event.job)
                self._add_job_node(event.job)

            if event.kind == JOB_START:
                job.status = "running"
            elif event.kind == JOB_END:
                job.status = event.status or job.status
                job.duration_s = event.duration_s
            elif event.kind == STEP_START:
                self._step(job, event.step).status = "running"
                if self._follow:
                    self._selected = (event.job, event.step)
                    self._repaint_log()
            elif event.kind == STEP_END:
                step = self._step(job, event.step)
                step.status = event.status or step.status
                step.duration_s = event.duration_s
            elif event.step and not _is_directive(event.text):
                step = self._step(job, event.step)
                step.lines.append((event.stream, event.text))
                del step.lines[:-MAX_LINES_PER_STEP]
                if self._selected == (event.job, event.step):
                    self._write_line(event.stream, event.text)
            self._refresh_labels(event.job)

        def _step(self, job: _Job, name: str) -> _Step:
            step = job.steps.get(name)
            if step is None:
                step = _Step(name=name)
                job.steps[name] = step
                job.order.append(name)
                self._add_step_node(job.name, name)
            return step

        # -- the tree ---------------------------------------------------------

        def _add_job_node(self, job: str) -> None:
            tree = self.query_one("#tree", Tree)
            node = tree.root.add(job, data=(job, ""), expand=True)
            self._tree_nodes[(job, "")] = node

        def _add_step_node(self, job: str, step: str) -> None:
            parent = self._tree_nodes.get((job, ""))
            if parent is None:
                return
            self._tree_nodes[(job, step)] = parent.add_leaf(step, data=(job, step))

        def _refresh_labels(self, job_name: str) -> None:
            job = self._jobs[job_name]
            node = self._tree_nodes.get((job_name, ""))
            if node is not None:
                node.set_label(_label(job.name, job.status, job.duration_s, _JOB))
            for step_name in job.order:
                leaf = self._tree_nodes.get((job_name, step_name))
                if leaf is not None:
                    step = job.steps[step_name]
                    leaf.set_label(_label(step.name, step.status, step.duration_s, _STEP))

        # -- the log pane ------------------------------------------------------

        def _repaint_log(self) -> None:
            log = self.query_one("#log", RichLog)
            log.clear()
            if self._selected is None:
                return
            job_name, step_name = self._selected
            job = self._jobs.get(job_name)
            if job is None or step_name not in job.steps:
                return
            heading = Text()
            heading.append("── ", style=_DEEP)
            heading.append(job_name, style=f"bold {_JOB}")
            heading.append(" · ", style=_DEEP)
            heading.append(step_name, style=f"bold {_STEP}")
            heading.append(" ──", style=_DEEP)
            log.write(heading)
            for stream, text in job.steps[step_name].lines:
                self._write_line(stream, text)

        def _write_line(self, stream: str, text: str) -> None:
            """A `rich.Text`, never a markup string.

            `RichLog(markup=True)` would PARSE the step's own output, so a build
            printing `[error] failed` would have `[error]` eaten as a style tag
            — and one printing `[/]` would raise inside the renderer. Styling
            the object instead means the content is never parsed at all.
            """
            log = self.query_one("#log", RichLog)
            if stream == STDERR:
                log.write(Text(text, style="red"))
            elif stream == META:
                log.write(Text(text, style="dim italic"))
            else:
                log.write(Text(text))

        def _set_status(self) -> None:
            done = sum(1 for j in self._jobs.values() if j.status != "running")
            failed = sum(1 for j in self._jobs.values() if j.status == STATUS_FLOPPED)
            follow = "following" if self._follow else "pinned"
            bar = Text()
            bar.append(f"  {done}/{len(self._jobs)} jobs", style=f"bold {_SUN}")
            if failed:
                bar.append(f"  ·  {failed} flopped", style=f"bold {_BAD}")
            bar.append(f"  ·  {follow}", style=_WARM)
            bar.append("   [f] follow   [q] quit", style=_DEEP)
            self.query_one("#status", Static).update(bar)

except ImportError:  # pragma: no cover - textual is optional

    class _YeetApp:  # type: ignore[no-redef]
        def __init__(self, sink: DashboardSink) -> None:
            self._sink = sink

        def run(self) -> None:
            return None


def _is_directive(text: str) -> bool:
    """`::group::` / `::endgroup::` are folding MARKERS, not output.

    The streaming renderers use them to indent; a pane that already has one
    step per view has nothing to fold, so they would just be two lines of
    noise at the top and bottom of every step.
    """
    stripped = text.strip()
    return stripped.startswith("::group::") or stripped == "::endgroup::"


def _label(name: str, status: str, duration_s: float | None, resting: str) -> Any:
    """One tree row: glyph, name, duration — coloured by what it is doing.

    A RUNNING row takes the lit sun at the baseline of the wordmark, which is
    what makes the live row findable in a forty-leg matrix without reading a
    single label. Everything else sits at its own depth in the gradient:
    indigo for a job, magenta for a step.

    Returns a `rich.Text` when Textual is installed (the only time this is
    called) so the name is never parsed as markup — a step called
    `build [prod]` must not lose its brackets.
    """
    glyph, style = {
        STATUS_SLAYED: (SYMBOL_PASS, f"bold {_OK}"),
        STATUS_FLOPPED: (SYMBOL_FAIL, f"bold {_BAD}"),
        "skipped": (SYMBOL_SKIP, "dim"),
        "cancelled": (SYMBOL_SKIP, "dim"),
    }.get(status, (SYMBOL_RUNNING, f"bold {_SUN}"))

    text = Text()
    text.append(f"{glyph} ", style=style)
    text.append(name, style=style if status == "running" else resting)
    if duration_s is not None:
        text.append(f"  {duration_s:.1f}s", style=_DEEP)
    return text
