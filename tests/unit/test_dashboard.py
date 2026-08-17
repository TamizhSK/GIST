"""`yeet run --tui` — the Textual dashboard.

Driven through Textual's own `run_test` harness rather than a pty: it renders
the real widget tree into a headless screen, so these assert what a user would
see instead of what the code intended.
"""

from __future__ import annotations

import pytest

from yeet.core.events import STDERR, STDOUT, LogEvent
from yeet.reporting import dashboard

pytestmark = pytest.mark.skipif(not dashboard.is_available(), reason="textual not installed")


def _screen(app, width: int = 90, height: int = 14) -> str:
    import io

    from rich.console import Console

    buf = io.StringIO()
    Console(file=buf, width=width, height=height, force_terminal=False).print(
        app.screen._compositor
    )
    return buf.getvalue()


@pytest.mark.asyncio
async def test_the_tree_shows_every_job_and_step_with_its_status() -> None:
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        sink.emit(LogEvent.step_ended("build", "compile", status="slayed", duration_s=1.5))
        sink.emit(LogEvent.job_ended("build", status="slayed", duration_s=2.0))
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "build" in screen
    assert "compile" in screen
    assert "[OK]" in screen, screen
    assert "1.5s" in screen, "a finished step must show what it cost"


@pytest.mark.asyncio
async def test_output_lands_in_the_pane_for_the_running_step() -> None:
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        sink.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="hello there"))
        sink.emit(LogEvent.now(job="build", step="compile", stream=STDERR, text="a warning"))
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "hello there" in screen
    assert "a warning" in screen


@pytest.mark.asyncio
async def test_group_directives_are_not_shown_as_output() -> None:
    """`::group::` is a folding MARKER the streaming renderers use to indent.
    A pane showing one step at a time has nothing to fold, so they would be two
    lines of noise around every step."""
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        sink.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="::group::compile"))
        sink.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="real output"))
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "real output" in screen
    assert "::group::" not in screen


@pytest.mark.asyncio
async def test_a_step_name_with_brackets_is_not_parsed_as_markup() -> None:
    """`RichLog(markup=True)` would eat `[prod]` as a style tag, and a step
    printing `[/]` would raise inside the renderer. Content is styled as a
    `Text` object, never parsed."""
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "deploy [prod]"))
        sink.emit(
            LogEvent.now(job="build", step="deploy [prod]", stream=STDOUT, text="[error] nope")
        )
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "[prod]" in screen, "the step name must keep its brackets"
    assert "[error] nope" in screen, "so must the step's own output"


@pytest.mark.asyncio
async def test_the_status_bar_counts_finished_and_failed_jobs() -> None:
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        for job in ("a", "b", "c"):
            sink.emit(LogEvent.job_started(job))
        sink.emit(LogEvent.job_ended("a", status="slayed", duration_s=1.0))
        sink.emit(LogEvent.job_ended("b", status="flopped", duration_s=1.0))
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "2/3 jobs" in screen
    assert "1 flopped" in screen


@pytest.mark.asyncio
async def test_a_run_that_finishes_between_frames_is_still_drawn_in_full() -> None:
    """The whole run can land in the queue before Textual has mounted.

    A `cooked_on: local` flow returns in milliseconds, so every event of it is
    queued before the first 20 Hz drain tick. The dashboard must show that run
    in full, not an empty tree — this is the shape of the bug that made `--tui`
    render one frame reading "starting…" and then close.
    """
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    # Everything queued BEFORE the app exists, and the worker already gone.
    sink.emit(LogEvent.job_started("build"))
    sink.emit(LogEvent.step_started("build", "compile"))
    sink.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="hello there"))
    sink.emit(LogEvent.step_ended("build", "compile", status="slayed", duration_s=1.5))
    sink.emit(LogEvent.job_ended("build", status="slayed", duration_s=2.0))
    sink._finished.set()

    async with app.run_test(size=(90, 14)) as pilot:
        await pilot.pause(0.4)
        screen = _screen(app)

    assert "compile" in screen, "the run must be on screen, not lost to the queue"
    assert "hello there" in screen
    assert "run finished" in screen
    assert "starting…" not in screen


@pytest.mark.asyncio
async def test_a_run_is_not_called_finished_with_events_still_queued() -> None:
    """`_finished` means the worker returned, not that the screen is current.

    Treating the two as the same is the ordering mistake that lost the run in
    the first place, one layer down.
    """
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(90, 14)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        await pilot.pause(0.4)
        assert not app._run_done, "a running job is not a finished run"
        sink._finished.set()
        await pilot.pause(0.4)
        assert app._run_done
        screen = _screen(app)

    assert "run finished" in screen


@pytest.mark.asyncio
@pytest.mark.parametrize(("width", "height"), [(176, 50), (120, 40), (100, 30), (80, 24)])
async def test_the_output_pane_is_never_the_smaller_half(width: int, height: int) -> None:
    """The log is what you are reading; the tree is how you navigate it.

    A fixed-width sidebar spends its columns out of the log's share, and at
    80x24 — still the commonest terminal size there is — 44 of 80 columns went
    to the tree and the step's own output was cut mid-word.
    """
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(width, height)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        await pilot.pause(0.4)
        tree_w = app.query_one("#tree").size.width
        log_w = app.query_one("#log").size.width
        assert "narrow" not in app.query_one("#body").classes
    assert log_w > tree_w, f"at {width}x{height} the tree took {tree_w} of {width} columns"


@pytest.mark.asyncio
@pytest.mark.parametrize(("width", "height"), [(64, 20), (46, 16), (40, 12)])
async def test_a_narrow_terminal_stacks_the_panes_rather_than_starving_one(
    width: int, height: int
) -> None:
    """Side by side, a 46-column terminal gave the log pane two columns — which
    is not a small log pane, it is no log pane. Stacked, both get full width."""
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(width, height)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        sink.emit(LogEvent.step_started("build", "compile"))
        sink.emit(LogEvent.now(job="build", step="compile", stream=STDOUT, text="hello there"))
        await pilot.pause(0.4)
        assert "narrow" in app.query_one("#body").classes
        log = app.query_one("#log")
        tree = app.query_one("#tree")
        # `size` is the CONTENT region, so both panes are the terminal width
        # less their own `padding: 0 1`.
        assert log.size.width == tree.size.width, "stacked panes get the same width"
        assert log.size.width >= width - 2, f"{log.size.width} of {width} columns"
        assert log.size.height >= 3, "the log must keep enough rows to be worth reading"
        screen = _screen(app, width=width, height=height)

    assert "hello there" in screen, "the step's output must survive a narrow terminal"


@pytest.mark.asyncio
async def test_the_layout_follows_a_terminal_resized_mid_run() -> None:
    """A window is dragged DURING a run more often than anyone plans for, so the
    layout cannot be something chosen once at startup."""
    sink = dashboard.DashboardSink(workflow_name="demo")
    app = dashboard._YeetApp(sink)

    async with app.run_test(size=(120, 40)) as pilot:
        sink.emit(LogEvent.job_started("build"))
        await pilot.pause(0.3)
        assert "narrow" not in app.query_one("#body").classes

        await pilot.resize_terminal(56, 20)
        await pilot.pause(0.3)
        assert "narrow" in app.query_one("#body").classes, "shrinking must stack the panes"

        await pilot.resize_terminal(120, 40)
        await pilot.pause(0.3)
        assert "narrow" not in app.query_one("#body").classes, "and growing must undo it"


class _StubApp:
    """Stands in for `_YeetApp` in the two `run_dashboard` tests.

    The real app owns the main thread and now sits there until `q`, so the
    orchestration around it is tested against a stub that returns as soon as
    the worker signals — the same moment the real one starts waiting.
    """

    seen: list[str] = []

    def __init__(self, sink: dashboard.DashboardSink) -> None:
        self._sink = sink

    def run(self) -> None:
        _StubApp.seen.append("run")
        self._sink._finished.wait(5)

    def call_from_thread(self, fn: object, *args: object) -> None:
        _StubApp.seen.append("call_from_thread")

    def exit(self) -> None:  # pragma: no cover - reached only through the stub
        _StubApp.seen.append("exit")


def test_a_finished_run_leaves_the_dashboard_up_to_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run_dashboard` must NOT exit the app when the run returns.

    It used to, and that exit raced the mount: the app was told to close with
    every event still in the queue. The worker signals completion instead, and
    the app closes on `q`.
    """
    _StubApp.seen = []
    monkeypatch.setattr(dashboard, "_YeetApp", _StubApp)

    sink = dashboard.DashboardSink(workflow_name="demo")
    result = dashboard.run_dashboard(sink, lambda: "the plan result")

    assert result == "the plan result"
    assert sink._finished.is_set()
    assert "call_from_thread" not in _StubApp.seen, "a finished run must not close the dashboard"


def test_a_crashed_run_closes_the_dashboard_and_re_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A traceback held hostage behind a keypress is worse than a vanished
    dashboard, so the crash path keeps the immediate exit."""
    _StubApp.seen = []
    monkeypatch.setattr(dashboard, "_YeetApp", _StubApp)

    def boom() -> str:
        raise RuntimeError("the backend fell over")

    sink = dashboard.DashboardSink(workflow_name="demo")
    with pytest.raises(RuntimeError, match="the backend fell over"):
        dashboard.run_dashboard(sink, boom)

    assert "call_from_thread" in _StubApp.seen, "a crash must tear the screen down"


def test_the_sink_never_blocks_a_worker_thread() -> None:
    """`emit` is called from the runner's job threads. A renderer that stalls
    them has changed the thing it was meant to observe — so it enqueues and
    returns, with no app running at all."""
    sink = dashboard.DashboardSink(workflow_name="demo")

    for index in range(1000):
        sink.emit(LogEvent.now(job="j", step="s", stream=STDOUT, text=f"line {index}"))

    assert sink._events.qsize() == 1000
