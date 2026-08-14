"""Log events and the sink Protocol the executor writes to.

Same tier problem as `core/masking.py`: the executor must persist run logs, but
`executor` and `storage` are independent siblings at tier 5. So the executor
does not import `storage` — it takes a `LogSink` and calls `emit()`. The CLI is
what decides that the sink is a JSONL file, a live rich tree, or both.

The useful side effect: the executor is testable with a list-appending fake and
no filesystem at all.

Owner: Dev C + Dev D
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

STDOUT = "stdout"
STDERR = "stderr"
META = "meta"
"""`meta` is ours, not the process's: step boundaries, `::group::` markers,
image pulls. Keeping it in the same stream lets `yeet logs` replay a run in
true chronological order instead of interleaving two files by guesswork."""

LOG = "log"
JOB_START = "job_start"
JOB_END = "job_end"
STEP_START = "step_start"
STEP_END = "step_end"
"""`kind` vocabulary. `LOG` is a line of text (the only kind that existed
before the live renderer): a `::group::` marker, a stdout/stderr line, a META
note. The other four are lifecycle events with no text of their own — they
carry `status`/`duration_s`/`exit_code` instead, so a renderer can draw a
spinner on `*_START` and freeze it into a ✓/✗ with a time on `*_END` without
having to infer job/step boundaries from the first line of output, the way
`reporting.console.RunConsole` used to."""


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One line of output, or one lifecycle transition. Serialized to JSONL
    verbatim — field names are the on-disk log format, so renaming one breaks
    `yeet logs` on old runs. New fields are additive and default such that a
    pre-lifecycle-events log file still replays: `kind` defaults to `LOG` and
    the rest to `None`."""

    ts: float
    job: str
    step: str
    stream: str
    text: str
    kind: str = LOG
    status: str | None = None
    """A `core.result.Status` value (e.g. `"slayed"`), set on `*_END` events."""
    duration_s: float | None = None
    exit_code: int | None = None
    """Only ever set on `STEP_END` — a job has no exit code of its own."""

    @classmethod
    def now(cls, job: str, step: str, stream: str, text: str) -> LogEvent:
        return cls(ts=time.time(), job=job, step=step, stream=stream, text=text)

    @classmethod
    def job_started(cls, job: str) -> LogEvent:
        return cls(ts=time.time(), job=job, step="", stream=META, text="", kind=JOB_START)

    @classmethod
    def job_ended(cls, job: str, *, status: str, duration_s: float) -> LogEvent:
        return cls(
            ts=time.time(),
            job=job,
            step="",
            stream=META,
            text="",
            kind=JOB_END,
            status=status,
            duration_s=duration_s,
        )

    @classmethod
    def step_started(cls, job: str, step: str) -> LogEvent:
        return cls(ts=time.time(), job=job, step=step, stream=META, text="", kind=STEP_START)

    @classmethod
    def step_ended(
        cls,
        job: str,
        step: str,
        *,
        status: str,
        duration_s: float,
        exit_code: int | None = None,
    ) -> LogEvent:
        return cls(
            ts=time.time(),
            job=job,
            step=step,
            stream=META,
            text="",
            kind=STEP_END,
            status=status,
            duration_s=duration_s,
            exit_code=exit_code,
        )


@runtime_checkable
class LogSink(Protocol):
    """Implemented by `storage.runs.RunStore` and `reporting.console.RunConsole`."""

    def emit(self, event: LogEvent) -> None: ...


@dataclass
class FanOut:
    """Write one event to several sinks. `cmd_run` builds one of these.

    A failing sink must not take down a run: a full disk should cost you the
    log file, not the build. Failures are counted, not raised.
    """

    sinks: list[LogSink] = field(default_factory=list)
    failures: int = 0

    def emit(self, event: LogEvent) -> None:
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:  # noqa: BLE001 - a broken sink must not kill the run
                self.failures += 1


@dataclass
class ListSink:
    """The test double. Keeps events in memory so executor tests need no disk."""

    events: list[LogEvent] = field(default_factory=list)

    def emit(self, event: LogEvent) -> None:
        self.events.append(event)

    def text(self) -> str:
        return "".join(e.text for e in self.events)
