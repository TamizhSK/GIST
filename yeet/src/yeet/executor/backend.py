"""Protocol both backends implement. Keeps Docker out of everyone else's imports.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from yeet.core.events import LogSink
from yeet.core.masking import Masker
from yeet.core.result import JobResult
from yeet.planner.plan import JobInstance


@dataclass
class JobContext:
    """Everything a job needs that is not in the Job itself.

    `secrets` is a Masker, not a dict: the executor's job is to redact values,
    not to know them. And `sink` is a Protocol rather than a storage object, so
    the executor never imports `storage` (they are independent siblings at
    tier 5 — lint-imports rejects that edge). Both indirections exist for the
    tier rule and both make this class trivial to fake in a test.
    """

    workspace: Path
    env: dict[str, str] = field(default_factory=dict)
    secrets: Masker = field(default_factory=Masker)
    sink: LogSink | None = None
    needs: dict[str, JobResult] = field(default_factory=dict)
    event: str = "push"


@runtime_checkable
class Backend(Protocol):
    def run_job(self, inst: JobInstance, ctx: JobContext) -> JobResult: ...
