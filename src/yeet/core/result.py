"""Execution result types. The executor produces these; reporting renders them.

Owner: Dev C + Dev D
Tier: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):  # noqa: UP042 - frozen contract; StrEnum changes str()
    PENDING = "pending"
    RUNNING = "cooked"
    SUCCESS = "slayed"
    FAILURE = "flopped"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self not in (Status.PENDING, Status.RUNNING)

    @property
    def ok(self) -> bool:
        return self in (Status.SUCCESS, Status.SKIPPED)


@dataclass
class StepResult:
    step_name: str
    status: Status = Status.PENDING
    exit_code: int | None = None
    duration_s: float = 0.0
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResult:
    job_key: str
    matrix_leg: dict[str, object] = field(default_factory=dict)
    status: Status = Status.PENDING
    steps: list[StepResult] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    duration_s: float = 0.0


@dataclass
class RunResult:
    run_id: str
    workflow_name: str
    jobs: list[JobResult] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def status(self) -> Status:
        if any(j.status is Status.FAILURE for j in self.jobs):
            return Status.FAILURE
        if all(j.status.ok for j in self.jobs):
            return Status.SUCCESS
        return Status.FAILURE

    @property
    def exit_code(self) -> int:
        return 0 if self.status is Status.SUCCESS else 1
