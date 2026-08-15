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


def test_the_sink_never_blocks_a_worker_thread() -> None:
    """`emit` is called from the runner's job threads. A renderer that stalls
    them has changed the thing it was meant to observe — so it enqueues and
    returns, with no app running at all."""
    sink = dashboard.DashboardSink(workflow_name="demo")

    for index in range(1000):
        sink.emit(LogEvent.now(job="j", step="s", stream=STDOUT, text=f"line {index}"))

    assert sink._events.qsize() == 1000
