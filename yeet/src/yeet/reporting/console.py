"""Live rich/console tree for a run: jobs, steps, timings, status glyphs.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import sys
from typing import TextIO

from yeet.core.events import META, STDERR, LogEvent
from yeet.reporting.theme import (
    STATUS_COOKED,
    STATUS_FLOPPED,
    STATUS_SLAYED,
    SYMBOL_FAIL,
    SYMBOL_PASS,
    SYMBOL_RUNNING,
    Colors,
    colorize,
)


class RunConsole:
    """Implements `core.events.LogSink`. The executor knows nothing about rich/console formatting.

    `::group::` opens a collapsible section; `::endgroup::` closes it. Status
    vocabulary comes from `theme.py` — slayed / flopped / mid / cooked /
    skipped (not the vibe).
    """

    def __init__(self, out: TextIO | None = None, *, color: bool = True) -> None:
        self.out = out if out is not None else sys.stdout
        self.color = color
        self._group_depth = 0
        self._current_job: str | None = None
        self._current_step: str | None = None

    def emit(self, event: LogEvent) -> None:
        text = event.text.rstrip("\r\n")

        # Headers FIRST, directives second. The executor opens a `::group::` as
        # the first event of every step, so handling directives first meant the
        # very first thing a run printed was a group header floating above the
        # job it belonged to:
        #
        #     ▼ say hi          <- group, printed before its own job
        #     ● build [cooked]
        #       ├─ ● say hi
        #
        # Tracking the job/step header before the early `return` puts the tree
        # back in the order the guide draws it.
        self._headers(event)

        if text.startswith("::group::"):
            group_name = text[len("::group::") :].strip()
            # `steps.py` names the group after the step, so a group header here
            # would just repeat the step header printed a moment ago. Track the
            # depth, print nothing. A group the user opened themselves inside a
            # `run:` block has a different name, and does get a header.
            if group_name != event.step:
                indent = "  " * (self._group_depth + 2)
                group_header = colorize(
                    f"▼ {group_name}", Colors.BOLD + Colors.CYAN, color=self.color
                )
                self._print(f"{indent}{group_header}")
            self._group_depth += 1
            return
        elif text == "::endgroup::":
            if self._group_depth > 0:
                self._group_depth -= 1
            return

        indent = "  " * (self._group_depth + 2)

        if event.stream == STDERR:
            formatted_text = colorize(text, Colors.RED, color=self.color)
            self._print(f"{indent}{formatted_text}")
        elif event.stream == META:
            formatted_text = colorize(text, Colors.DIM + Colors.ITALIC, color=self.color)
            self._print(f"{indent}{formatted_text}")
        else:
            self._print(f"{indent}{text}")

    def _headers(self, event: LogEvent) -> None:
        """Print the job and step headers when either changes."""
        if event.job != self._current_job:
            self._current_job = event.job
            self._current_step = None
            self._group_depth = 0
            job_hdr = colorize(
                f"{SYMBOL_RUNNING} {event.job}", Colors.BOLD + Colors.BLUE, color=self.color
            )
            tag = colorize(f"[{STATUS_COOKED}]", Colors.DIM, color=self.color)
            self._print(f"\n{job_hdr} {tag}")

        if event.step and event.step != self._current_step:
            self._current_step = event.step
            step_hdr = colorize(
                f"  ├─ {SYMBOL_RUNNING} {event.step}", Colors.CYAN, color=self.color
            )
            self._print(step_hdr)

    def _print(self, msg: str) -> None:
        try:
            self.out.write(msg + "\n")
            self.out.flush()
        except Exception:
            pass

    def render_summary(
        self,
        workflow_name: str,
        status: str,
        duration_s: float,
    ) -> None:
        """Render the final run summary block."""
        if status == STATUS_SLAYED:
            status_str = colorize(
                f"{SYMBOL_PASS} {STATUS_SLAYED.upper()}",
                Colors.BOLD + Colors.GREEN,
                color=self.color,
            )
        elif status == STATUS_FLOPPED:
            status_str = colorize(
                f"{SYMBOL_FAIL} {STATUS_FLOPPED.upper()}",
                Colors.BOLD + Colors.RED,
                color=self.color,
            )
        else:
            status_str = colorize(status.upper(), Colors.BOLD + Colors.YELLOW, color=self.color)

        summary = f"\nflow: {workflow_name} — {status_str} in {duration_s:.1f}s"
        self._print(summary)
