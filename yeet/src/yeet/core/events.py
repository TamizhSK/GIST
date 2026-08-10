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


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One line of output. Serialized to JSONL verbatim — field names are the
    on-disk log format, so renaming one breaks `yeet logs` on old runs."""

    ts: float
    job: str
    step: str
    stream: str
    text: str

    @classmethod
    def now(cls, job: str, step: str, stream: str, text: str) -> LogEvent:
        return cls(ts=time.time(), job=job, step=step, stream=stream, text=text)


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
