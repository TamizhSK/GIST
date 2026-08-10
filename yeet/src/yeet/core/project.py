"""What the analyzer learned about a directory, before any YAML is parsed.

Lives in core rather than `analyzer/` because `reporting/` (tier 1) formats a
Project for `yeet scan`, and tier 1 may not import tier 2. Keeping the type
down here means the renderer stays a pure function of data.

Owner: Dev A
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Ecosystem:
    """One detected stack. A polyglot repo yields several of these."""

    name: str  # "python", "node", "go", ...
    marker: Path  # the file that proved it, for the scan report
    suggested_image: str  # "python:3.12"
    default_commands: list[str] = field(default_factory=list)  # for `init --auto`
    version: str | None = None  # read from engines.node / requires-python


@dataclass
class Project:
    """The result of `analyzer.project.analyze()`.

    `flows` is in precedence order: `.yeet/flows/` before `.github/workflows/`
    before a root `yeet.yml`. `foreign_ci` is deliberately separate — a
    `.gitlab-ci.yml` is worth reporting as unsupported rather than ignoring in
    silence, and it must never be fed to the parser.
    """

    root: Path
    flows: list[Path] = field(default_factory=list)
    foreign_ci: list[Path] = field(default_factory=list)
    ecosystems: list[Ecosystem] = field(default_factory=list)
    is_git: bool = False
    branch: str | None = None
    dockerfile: Path | None = None
    truncated: bool = False
    """True when discovery hit MAX_FILES and stopped. The scan report has to say
    so — silently reporting half a monorepo is worse than reporting none of it."""

    @property
    def has_flows(self) -> bool:
        return bool(self.flows)

    @property
    def stack(self) -> str:
        """One-line summary for the scan header: `Python 3.12 · Docker`."""
        parts = [f"{e.name}{' ' + e.version if e.version else ''}" for e in self.ecosystems]
        if self.dockerfile is not None:
            parts.append("Docker")
        return " · ".join(parts) if parts else "unknown"
