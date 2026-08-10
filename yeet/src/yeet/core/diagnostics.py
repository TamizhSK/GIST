"""FROZEN CONTRACT #1 — the diagnostic type.

Every subsystem emits these. Only `reporting` renders them.
Nobody calls print() for an error. Ever.

Owner: whole team (changes need everyone's sign-off)
Tier: 0 — imports nothing from this package
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"      # blocks execution
    WARNING = "warning"  # blocks only under --strict
    INFO = "info"        # never blocks

    @property
    def rank(self) -> int:
        return {"error": 2, "warning": 1, "info": 0}[self.value]


@dataclass(frozen=True, slots=True)
class Position:
    """0-indexed line, 0-indexed column. Rendered as 1-indexed."""
    line: int
    col: int
    end_col: int | None = None

    @classmethod
    def unknown(cls) -> "Position":
        return cls(line=-1, col=-1)

    @property
    def is_known(self) -> bool:
        return self.line >= 0


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str                       # "YEET-E301"
    severity: Severity
    message: str                    # one line, plain language, no jargon
    file: Path | None = None
    pos: Position | None = None
    help: str | None = None         # "did you mean `build`?"
    note: str | None = None         # extra context, optional
    url: str | None = None          # docs/rules.md#yeet-e301

    def __str__(self) -> str:       # fallback if the renderer ever fails
        loc = ""
        if self.file:
            loc = str(self.file)
            if self.pos and self.pos.is_known:
                loc += f":{self.pos.line + 1}:{self.pos.col + 1}"
            loc += ": "
        return f"{loc}{self.severity.value}[{self.code}] {self.message}"


@dataclass
class DiagnosticBag:
    """Collect-don't-raise. Validation layers append; the pipeline decides."""
    items: list[Diagnostic] = field(default_factory=list)

    def add(self, d: Diagnostic) -> None:
        self.items.append(d)

    def extend(self, ds: "list[Diagnostic] | DiagnosticBag") -> None:
        self.items.extend(ds.items if isinstance(ds, DiagnosticBag) else ds)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.WARNING]

    def has_errors(self) -> bool:
        return bool(self.errors)

    def exit_code(self, strict: bool = False) -> int:
        if self.errors:
            return 2
        if strict and self.warnings:
            return 2
        return 0

    def sorted(self) -> list[Diagnostic]:
        """Group by file, then by position, so the report reads top-to-bottom."""
        def key(d: Diagnostic):
            return (
                str(d.file or ""),
                d.pos.line if d.pos and d.pos.is_known else 1 << 30,
                d.pos.col if d.pos and d.pos.is_known else 0,
                d.code,
            )
        return sorted(self.items, key=key)

    def __len__(self) -> int:
        return len(self.items)
