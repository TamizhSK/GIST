"""Live rich tree for a run: jobs, steps, timings, status glyphs.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from yeet.core.events import LogEvent


class RunConsole:
    """Implements `core.events.LogSink`. The executor knows nothing about rich.

    `::group::` opens a collapsible section; `::endgroup::` closes it. Status
    vocabulary comes from `theme.py` — slayed / flopped / mid / cooked /
    skipped (not the vibe).
    """

    def emit(self, event: LogEvent) -> None:
        raise NotImplementedError
