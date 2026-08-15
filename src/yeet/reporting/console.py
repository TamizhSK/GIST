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
    STEP_END,
    STEP_START,
    LogEvent,
)
from yeet.reporting.theme import (
    BRANCH,
    PIPE,
    STATUS_COOKED,
    SYMBOL_FAIL,
    SYMBOL_PASS,
    SYMBOL_RUNNING,
    SYMBOL_SKIP,
    Colors,
    color_level,
    colorize,
    format_summary,
)


class RunConsole:
    """Implements `core.events.LogSink`. The executor knows nothing about rich/console formatting.

    `::group::` opens a collapsible section; `::endgroup::` closes it. Status
    vocabulary comes from `theme.py` — slayed / flopped / mid / cooked /
    skipped (not the vibe).

    `verbose` adds the `::group::` headers a step emitted. It does NOT gate the
    step's stdout/stderr, which is always printed.

    That distinction is the whole point of this class. There is no cursor here
    — this renderer is what a pipe, a redirect and a CI log get — so anything
    not printed is not hidden, it is gone, and no flag the user has already
    failed to pass can bring it back. `reporting.live` may collapse a finished
    step because it has a terminal to collapse into and `yeet logs` to replay
    from; this one may not. Suppressing output here meant `yeet run > out.txt`
    contained a tree of `[OK]`s and not one line of what the build actually
    said.
    """

    def __init__(
        self, out: TextIO | None = None, *, color: bool = True, verbose: bool = True
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.color = color
        self.verbose = verbose
        # Per JOB, not one shared counter. Jobs in a wave emit from parallel
        # threads, so a single `_group_depth` meant one job's `::group::`
        # silently indented another job's output — and `::endgroup::` from
        # either closed it.
        self._group_depth: dict[str, int] = {}
        self._seen_jobs: list[str] = []
        self._job_steps: dict[str, str] = {}
        self._label_width = 0

    def start(self) -> None:
        """No-op: a plain console has nothing to open. Exists so `cmd_run` can
        call `start()`/`stop()` on whichever sink `reporting.live.make_console`
        handed back without caring which one it got."""

    def stop(self) -> None:
        """See `start()`."""

    def emit(self, event: LogEvent) -> None:
        self._headers(event)

        if event.kind == JOB_END:
            self._footer(event.job, "", event.job, event.status, event.duration_s)
            return
        if event.kind == STEP_END:
            self._footer(event.job, f"  {BRANCH}", event.step, event.status, event.duration_s)
            return
        if event.kind in (JOB_START, STEP_START):
            # The header was already printed above, on first sight of this
            # job/step — a start event carries no text of its own.
            return

        text = event.text.rstrip("\r\n")
        depth = self._group_depth.get(event.job, 0)

        if text.startswith("::group::"):
            if not self.verbose:
                return
            group_name = text[len("::group::") :].strip()
            if group_name != event.step:
                header = colorize(f">> {group_name}", Colors.BOLD + Colors.CYAN, color=self.color)
                self._print(event.job, "  " * (depth + 2) + header)
            self._group_depth[event.job] = depth + 1
            return
        elif text == "::endgroup::":
            self._group_depth[event.job] = max(0, depth - 1)
            return

        indent = "  " * (depth + 2)

        if event.stream == STDERR:
            self._print(event.job, indent + colorize(text, Colors.RED, color=self.color))
        elif event.stream == META:
            style = Colors.DIM + Colors.ITALIC
            self._print(event.job, indent + colorize(text, style, color=self.color))
        else:
            self._print(event.job, indent + text)

    # -- attribution -----------------------------------------------------------

    def _prefix(self, job: str) -> str:
        """`job │ ` once a run has more than one job, and nothing before that.

        Parallel legs share one stream, and until this existed there was no way
        to tell which of them a line came from: a three-leg matrix printed
        three identical `+-- setup` headers and then `using node 16`, `using
        node 18` and `using node 20` in whatever order the threads got to the
        sink. Every line was true and the block as a whole said nothing.

        Nothing is prefixed while only one job has been seen, which keeps the
        common single-job run exactly as clean as it was — and it is safe,
        because a line emitted before a second job appeared could only have
        come from the first.
        """
        if len(self._seen_jobs) < 2:
            return ""
        bar = PIPE.strip() or "|"
        return colorize(f"{job:<{self._label_width}} {bar} ", Colors.DIM, color=self.color)

    def _headers(self, event: LogEvent) -> None:
        """Print each job and step header once, even when parallel legs interleave."""
        if event.job not in self._seen_jobs:
            self._seen_jobs.append(event.job)
            self._label_width = max(self._label_width, len(event.job))
            self._group_depth[event.job] = 0
            job_hdr = colorize(
                f"{SYMBOL_RUNNING} {event.job}", Colors.BOLD + Colors.BLUE, color=self.color
            )
            tag = colorize(f"[{STATUS_COOKED}]", Colors.DIM, color=self.color)
            self._print("", f"\n{job_hdr} {tag}")

        if event.step and self._job_steps.get(event.job) != event.step:
            self._job_steps[event.job] = event.step
            step_hdr = colorize(
                f"  {BRANCH}{SYMBOL_RUNNING} {event.step}", Colors.CYAN, color=self.color
            )
            self._print(event.job, step_hdr)

    def _footer(
        self, job: str, prefix: str, name: str, status: str | None, duration_s: float | None
    ) -> None:
        """The `[OK] name (0.2s)` line printed once a job or step lifecycle event
        reports its status — the plain-console answer to the live renderer's
        spinner-to-checkmark transition, just as its own line instead of an
        in-place repaint. `prefix` carries the same branch glyph (or lack of
        one) as `_headers` used for this row's opening line, so the icon lands
        in the same column the running marker did instead of jumping in front
        of the branch."""
        icon, style = _glyph(status)
        dur = f" ({duration_s:.1f}s)" if duration_s is not None else ""
        self._print(job, colorize(f"{prefix}{icon} {name}{dur}", style, color=self.color))

    def _print(self, job: str, msg: str) -> None:
        """`job` is "" for a line that owns the full width (a job header).

        A blank leading line keeps its blank: prefixing it would print a bare
        gutter with nothing after it, once per job, which reads as damage.
        """
        prefix = self._prefix(job) if job else ""
        lead = "\n" if prefix and msg.startswith("\n") else ""
        msg = lead + prefix + (msg[1:] if lead else msg)
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
            "",
            format_summary(
                workflow_name,
                status,
                duration_s,
                run_id=run_id,
                job_count=job_count,
                # Detected from the real stream rather than passed as a bool:
                # `self.color` is only permission, and a terminal that allows
                # colour may still be a 16-colour one.
                level=color_level(self.out, enabled=self.color),
                panel=False,
            ),
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
