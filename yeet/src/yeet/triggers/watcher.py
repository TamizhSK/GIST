"""watchdog daemon. DEBOUNCE or a run's own writes retrigger it forever.

Owner: Dev D
Tier: 6 — may import from: everything below tier 6
See docs/architecture.md

Three things here are not incidental:

1. **Debounce (500 ms).** An editor writing a file produces several events, and
   a `yeet run` triggered by one of them writes more. Without coalescing, the
   watcher feeds itself and never stops — risk register #7.

2. **What is ignored.** `.yeet/tmp`, `.yeet/runs`, `.yeet/artifacts` — the
   directories a *run* writes to — but explicitly NOT `.yeet/` as a whole. The
   previous version ignored every path with `.yeet` in it, which meant editing
   `.yeet/flows/main.yml` (the file the user is most likely to be editing, and
   the only reason to run `yeet watch` at all) triggered nothing.

3. **The per-project lock.** Two watchers on one project means two runs of the
   same workflow racing over the same `.yeet/tmp`. The lock is a file holding a
   pid; a stale one from a killed daemon is detected and taken over rather than
   left to block the project forever.

This module prints nothing and raises nothing at the caller. Output is the
CLI's job (`cmd_watch`), which is why `watch()` takes `on_error`.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

DEBOUNCE_MS = 500

#: Directory names never worth watching, at any depth.
IGNORED_DIRS = frozenset({".git", "node_modules", "target", "__pycache__", ".venv", ".mypy_cache"})

#: Paths *inside* `.yeet/` that a run writes to. Watching these is the feedback
#: loop in risk #7. `.yeet/flows/` is deliberately absent.
IGNORED_YEET_SUBDIRS = frozenset({"tmp", "runs", "artifacts", "cache"})

WATCHED_SUFFIXES = frozenset({".yml", ".yaml"})

LOCK_NAME = "watch.lock"


class LockHeld(RuntimeError):
    """Another watcher already holds this project."""


def is_relevant(path: Path) -> bool:
    """Is this a path a watcher should wake up for?

    Pure and total, so the interesting half of the watcher is unit-testable
    without a filesystem, a daemon or a sleep.
    """
    if path.suffix.lower() not in WATCHED_SUFFIXES:
        return False

    parts = path.parts
    if any(part in IGNORED_DIRS for part in parts):
        return False

    # `.yeet/tmp/...` and friends, but not `.yeet/flows/...`
    for index, part in enumerate(parts):
        if part == ".yeet" and index + 1 < len(parts) and parts[index + 1] in IGNORED_YEET_SUBDIRS:
            return False

    return True


@dataclass
class Debouncer:
    """Coalesce a burst of events into one dispatch per path.

    `submit()` records a path; `due()` returns the paths that have been quiet
    for `delay_s`. The clock is injected so a test can prove the timing without
    waiting for it.
    """

    delay_s: float = DEBOUNCE_MS / 1000.0
    clock: Callable[[], float] = time.monotonic
    _pending: dict[Path, float] = field(default_factory=dict)

    def submit(self, path: Path) -> None:
        self._pending[path] = self.clock()

    def due(self) -> list[Path]:
        now = self.clock()
        ready = [path for path, seen in self._pending.items() if now - seen >= self.delay_s]
        for path in ready:
            del self._pending[path]
        return sorted(ready)

    @property
    def pending(self) -> int:
        return len(self._pending)


class ProjectLock:
    """A pid file under `.yeet/`, so one project has one watcher.

    A stale lock (the pid is gone) is taken over. A daemon killed with -9 must
    not require the user to know about a lock file to start again.
    """

    def __init__(self, root: Path) -> None:
        self.path = root / ".yeet" / LOCK_NAME

    def acquire(self) -> None:
        if self.path.exists():
            holder = self._holder()
            if holder is not None and holder != os.getpid() and _pid_alive(holder):
                raise LockHeld(f"another `yeet watch` is running for this project (pid {holder})")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()), encoding="utf-8")

    def release(self) -> None:
        if self._holder() == os.getpid():
            with contextlib.suppress(OSError):
                self.path.unlink()

    def _holder(self) -> int | None:
        try:
            return int(self.path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def __enter__(self) -> ProjectLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return False
    return True


class _Handler(FileSystemEventHandler):
    def __init__(self, debouncer: Debouncer) -> None:
        self.debouncer = debouncer

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        for raw in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if not raw:
                continue
            path = Path(os.fsdecode(raw))
            if is_relevant(path):
                self.debouncer.submit(path)


def watch(
    paths: Iterable[Path],
    on_change: Callable[[Path], None],
    *,
    debounce_ms: int = DEBOUNCE_MS,
    on_error: Callable[[Exception], None] | None = None,
    poll_interval_s: float = 0.1,
    max_ticks: int | None = None,
) -> None:
    """Watch `paths`, calling `on_change(file)` once per settled change.

    Blocks until KeyboardInterrupt. `max_ticks` bounds the loop for tests.

    A failure inside `on_change` is reported through `on_error` and the daemon
    keeps running — a broken workflow file is the normal case for a watcher and
    must never take it down.
    """
    roots: Sequence[Path] = [Path(p).resolve() for p in paths]
    if not roots:
        return

    debouncer = Debouncer(delay_s=debounce_ms / 1000.0)
    observer = Observer()
    handler = _Handler(debouncer)
    for root in roots:
        observer.schedule(handler, str(root), recursive=True)

    lock = ProjectLock(roots[0])
    lock.acquire()
    observer.start()

    ticks = 0
    try:
        while max_ticks is None or ticks < max_ticks:
            ticks += 1
            time.sleep(poll_interval_s)
            for changed in debouncer.due():
                try:
                    on_change(changed)
                except Exception as exc:  # noqa: BLE001 - a bad file must not kill the daemon
                    if on_error is not None:
                        on_error(exc)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        with contextlib.suppress(Exception):
            observer.join(timeout=2.0)
        lock.release()
