"""Plain-line console renderer: jobs, steps, timings, status glyphs.

The non-interactive half of the pair with `reporting.live` — used whenever
stdout is not a real terminal (piped, redirected, `yeet logs` replay) since
`rich.live.Live`'s in-place repaint corrupts anything that isn't. Everything
here is a straight `write()` of one finished line at a time, so it is safe
under a pipe, a redirect, or a log file.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import sys
from typing import TextIO

from yeet.core.events import (
    JOB_END,
    JOB_START,
    META,
    STDERR,
    STDOUT,
    STEP_END,
    STEP_START,
    LogEvent,
)
from yeet.reporting.theme import (
    BRANCH,
    STATUS_COOKED,
    SYMBOL_FAIL,
    SYMBOL_PASS,
    SYMBOL_RUNNING,
    SYMBOL_SKIP,
    Colors,
    colorize,
    format_summary,
)


class RunConsole:
    """Implements `core.events.LogSink`. The executor knows nothing about rich/console formatting.

    `::group::` opens a collapsible section; `::endgroup::` closes it. Status
    vocabulary comes from `theme.py` — slayed / flopped / mid / cooked /
    skipped (not the vibe).

    `verbose` controls only the raw stdout/stderr body of a step, not its
    header/footer line: with `verbose=False` you still see every job and step
    with its final `[OK]`/`[FAIL]` and timing, just not the output in between — this
    terminal has no cursor to collapse a finished step's log into, the way
    `reporting.live` does, so "collapsed" here means "never printed" rather
    than "printed then hidden". `yeet logs` wants the opposite (it exists to
    show you everything), so it defaults to `True`.
    """

    def __init__(
        self, out: TextIO | None = None, *, color: bool = True, verbose: bool = True
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.color = color
        self.verbose = verbose
        self._group_depth = 0
        self._seen_jobs: set[str] = set()
        self._job_steps: dict[str, str] = {}

    def start(self) -> None:
        """No-op: a plain console has nothing to open. Exists so `cmd_run` can
        call `start()`/`stop()` on whichever sink `reporting.live.make_console`
        handed back without caring which one it got."""

    def stop(self) -> None:
        """See `start()`."""

    def emit(self, event: LogEvent) -> None:
        self._headers(event)

        if event.kind == JOB_END:
            self._footer("", event.job, event.status, event.duration_s)
            return
        if event.kind == STEP_END:
            self._footer(f"  {BRANCH}", event.step, event.status, event.duration_s)
            return
        if event.kind in (JOB_START, STEP_START):
            # The header was already printed above, on first sight of this
            # job/step — a start event carries no text of its own.
            return

        text = event.text.rstrip("\r\n")
        if not self.verbose and event.stream in (STDOUT, STDERR):
            return

        if text.startswith("::group::"):
            if not self.verbose:
                return
            group_name = text[len("::group::") :].strip()
            if group_name != event.step:
                indent = "  " * (self._group_depth + 2)
                group_header = colorize(
                    f">> {group_name}", Colors.BOLD + Colors.CYAN, color=self.color
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
        """Print each job and step header once, even when parallel legs interleave."""
        if event.job not in self._seen_jobs:
            self._seen_jobs.add(event.job)
            self._group_depth = 0
            job_hdr = colorize(
                f"{SYMBOL_RUNNING} {event.job}", Colors.BOLD + Colors.BLUE, color=self.color
            )
            tag = colorize(f"[{STATUS_COOKED}]", Colors.DIM, color=self.color)
            self._print(f"\n{job_hdr} {tag}")

        if event.step and self._job_steps.get(event.job) != event.step:
            self._job_steps[event.job] = event.step
            step_hdr = colorize(
                f"  {BRANCH}{SYMBOL_RUNNING} {event.step}", Colors.CYAN, color=self.color
            )
            self._print(step_hdr)

    def _footer(self, prefix: str, name: str, status: str | None, duration_s: float | None) -> None:
        """The `[OK] name (0.2s)` line printed once a job or step lifecycle event
        reports its status — the plain-console answer to the live renderer's
        spinner-to-checkmark transition, just as its own line instead of an
        in-place repaint. `prefix` carries the same branch glyph (or lack of
        one) as `_headers` used for this row's opening line, so the icon lands
        in the same column the running marker did instead of jumping in front
        of the branch."""
        icon, style = _glyph(status)
        dur = f" ({duration_s:.1f}s)" if duration_s is not None else ""
        self._print(colorize(f"{prefix}{icon} {name}{dur}", style, color=self.color))

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
        *,
        run_id: str = "",
        job_count: int = 0,
    ) -> None:
        """Render the final run summary block."""
        self._print(
            format_summary(
                workflow_name,
                status,
                duration_s,
                run_id=run_id,
                job_count=job_count,
                color=self.color,
            )
        )


def _glyph(status: str | None) -> tuple[str, str]:
    """`status` is a `core.result.Status` value — `"slayed"`, `"flopped"`,
    `"skipped"`, `"cancelled"`, or `None` for a status we don't recognise
    (never happens in practice, but a report must not crash over a glyph)."""
    if status == "slayed":
        return SYMBOL_PASS, Colors.BOLD + Colors.GREEN
    if status == "flopped":
        return SYMBOL_FAIL, Colors.BOLD + Colors.RED
    if status in ("skipped", "cancelled"):
        return SYMBOL_SKIP, Colors.DIM
    return SYMBOL_RUNNING, Colors.CYAN
