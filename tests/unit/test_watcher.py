"""D26 — the watcher's decisions, without waiting for a daemon.

The observer thread is watchdog's problem. What is ours is: which paths are
worth waking for, coalescing a burst into one dispatch, and not letting two
daemons fight over one project. All three are pure enough to test directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yeet.triggers.watcher import Debouncer, LockHeld, ProjectLock, is_relevant


class FakeClock:
    """A clock the test advances by hand, so a 500 ms debounce costs 0 ms."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- is_relevant -------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".yeet/flows/main.yml",
        ".github/workflows/ci.yml",
        "yeet.yml",
        "deploy.yaml",
    ],
)
def test_workflow_files_are_watched(path: str) -> None:
    assert is_relevant(Path(path)) is True


def test_yeet_flows_are_watched_even_though_they_live_under_dot_yeet() -> None:
    """The regression this rule exists for.

    The old watcher skipped every path containing `.yeet`, so editing the flow
    file — the entire reason to run `yeet watch` — triggered nothing at all.
    """
    assert is_relevant(Path("/repo/.yeet/flows/main.yml")) is True


@pytest.mark.parametrize(
    "path",
    [
        ".yeet/tmp/20260101-000000-abcd/build/step-0/script.yml",
        ".yeet/runs/20260101-000000-abcd/log.yml",
        ".yeet/artifacts/run/thing.yml",
        ".yeet/cache/thing.yml",
    ],
)
def test_run_output_is_ignored(path: str) -> None:
    """Risk #7: a run writes files; if those wake the watcher it runs forever."""
    assert is_relevant(Path(path)) is False


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/pkg/action.yml",
        ".git/something.yml",
        "target/debug/x.yml",
        ".venv/lib/thing.yml",
        "README.md",
        "src/main.py",
    ],
)
def test_noise_is_ignored(path: str) -> None:
    assert is_relevant(Path(path)) is False


# --- Debouncer ---------------------------------------------------------------


def test_a_burst_of_events_dispatches_once() -> None:
    clock = FakeClock()
    debouncer = Debouncer(delay_s=0.5, clock=clock)
    path = Path("flow.yml")

    for _ in range(5):  # an editor writing the same file five times
        debouncer.submit(path)
        clock.advance(0.05)

    assert debouncer.due() == []  # still settling

    clock.advance(0.5)
    assert debouncer.due() == [path]
    assert debouncer.due() == []  # and not a second time


def test_each_path_settles_independently() -> None:
    clock = FakeClock()
    debouncer = Debouncer(delay_s=0.5, clock=clock)

    debouncer.submit(Path("a.yml"))
    clock.advance(0.4)
    debouncer.submit(Path("b.yml"))
    clock.advance(0.2)  # a.yml has been quiet 0.6s, b.yml only 0.2s

    assert debouncer.due() == [Path("a.yml")]
    assert debouncer.pending == 1

    clock.advance(0.5)
    assert debouncer.due() == [Path("b.yml")]


# --- ProjectLock -------------------------------------------------------------


def test_lock_is_released_on_exit(tmp_path: Path) -> None:
    lock = ProjectLock(tmp_path)
    with lock:
        assert lock.path.exists()
    assert not lock.path.exists()


def test_a_second_live_watcher_is_refused(tmp_path: Path) -> None:
    """A live holder that is not us blocks — that is the two-terminals case.

    The lock is deliberately re-entrant for our *own* pid: one process holding
    it twice is the same daemon, and self-deadlocking there would be a bug, not
    a safeguard.
    """
    held = tmp_path / ".yeet" / "watch.lock"
    held.parent.mkdir(parents=True)
    held.write_text(str(os.getppid()), encoding="utf-8")  # alive, and not us

    with pytest.raises(LockHeld):
        ProjectLock(tmp_path).acquire()


def test_the_lock_is_reentrant_for_its_own_process(tmp_path: Path) -> None:
    with ProjectLock(tmp_path):
        ProjectLock(tmp_path).acquire()  # same pid — must not raise


def test_a_stale_lock_is_taken_over(tmp_path: Path) -> None:
    """A daemon killed with -9 must not need a manual `rm` to restart."""
    stale = tmp_path / ".yeet" / "watch.lock"
    stale.parent.mkdir(parents=True)
    stale.write_text("999999999", encoding="utf-8")  # a pid that cannot be alive

    lock = ProjectLock(tmp_path)
    lock.acquire()
    assert lock.path.read_text(encoding="utf-8") == str(os.getpid())
    lock.release()


def test_a_corrupt_lock_does_not_wedge_the_project(tmp_path: Path) -> None:
    corrupt = tmp_path / ".yeet" / "watch.lock"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not a pid", encoding="utf-8")

    lock = ProjectLock(tmp_path)
    lock.acquire()  # must not raise
    lock.release()
