"""THE code-frame renderer. rustc/eslint style. Must never itself crash.

Owner: Dev D
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Severity
from yeet.reporting.theme import Colors, colorize, use_color

CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1


def render_diagnostics(bag: DiagnosticBag, *, color: bool = True) -> str:
    """Clamp every index. Wrap in try/except and fall back to str(diagnostic).

    Risk #20 on the guide's list: the error reporter must never be the thing
    that errors. A bad line/col from a half-built IR node has to degrade to
    `file:line: message`, not take down the whole report.

    Disable color when NO_COLOR is set or stdout is not a TTY.
    """
    enable_color = color and use_color()
    if not bag.items:
        return ""

    file_cache: dict[Path, list[str]] = {}
    outputs: list[str] = []

    for diag in bag.sorted():
        try:
            rendered = _render_single_diagnostic(diag, file_cache, color=enable_color)
            outputs.append(rendered)
        except Exception:
            outputs.append(str(diag))

    return "\n\n".join(outputs)


def _render_single_diagnostic(
    diag: Diagnostic, file_cache: dict[Path, list[str]], *, color: bool
) -> str:
    # Color definitions for severity
    if diag.severity == Severity.ERROR:
        sev_color = Colors.BRIGHT_RED
        sev_text = "error"
    elif diag.severity == Severity.WARNING:
        sev_color = Colors.BRIGHT_YELLOW
        sev_text = "warning"
    else:
        sev_color = Colors.BRIGHT_CYAN
        sev_text = "info"

    hdr_sev = colorize(f"{sev_text}[{diag.code}]", sev_color + Colors.BOLD, color=color)
    hdr_msg = colorize(diag.message, Colors.BOLD, color=color)
    lines: list[str] = [f"{hdr_sev}: {hdr_msg}"]

    file_path = diag.file
    pos = diag.pos

    if file_path:
        loc_str = str(file_path)
        if pos and pos.is_known:
            loc_str += f":{pos.line + 1}:{pos.col + 1}"
        arrow = colorize("-->", Colors.BRIGHT_BLUE + Colors.BOLD, color=color)
        lines.append(f" {arrow} {loc_str}")

        # Try to read file lines
        if file_path not in file_cache:
            try:
                file_cache[file_path] = file_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except Exception:
                file_cache[file_path] = []

        file_lines = file_cache.get(file_path, [])
        if pos and pos.is_known and file_lines:
            target_line_idx = max(0, min(pos.line, len(file_lines) - 1))
            start_line_idx = max(0, target_line_idx - CONTEXT_BEFORE)
            end_line_idx = min(len(file_lines) - 1, target_line_idx + CONTEXT_AFTER)

            max_lineno_width = len(str(end_line_idx + 1))
            pipe = colorize("|", Colors.BRIGHT_BLUE + Colors.BOLD, color=color)
            gutter_pad = " " * max_lineno_width

            lines.append(f"{gutter_pad} {pipe}")

            for idx in range(start_line_idx, end_line_idx + 1):
                lineno = idx + 1
                lineno_str = str(lineno).rjust(max_lineno_width)
                line_content = file_lines[idx]

                gutter_num = colorize(lineno_str, Colors.BRIGHT_BLUE, color=color)
                lines.append(f"{gutter_num} {pipe} {line_content}")

                if idx == target_line_idx:
                    # Caret underline
                    col = max(0, min(pos.col, len(line_content)))
                    end_col = pos.end_col if pos.end_col is not None else col + 1
                    end_col = max(col + 1, min(end_col, len(line_content) + 1))

                    span_len = max(1, end_col - col)
                    caret_str = "^" * span_len
                    caret_colored = colorize(caret_str, sev_color + Colors.BOLD, color=color)
                    lines.append(f"{gutter_pad} {pipe} {' ' * col}{caret_colored}")

            lines.append(f"{gutter_pad} {pipe}")

    # Extra help / note sections
    if diag.help:
        help_prefix = colorize("= help:", Colors.BRIGHT_CYAN + Colors.BOLD, color=color)
        lines.append(f"   {help_prefix} {diag.help}")

    if diag.note:
        note_prefix = colorize("= note:", Colors.DIM + Colors.BOLD, color=color)
        lines.append(f"   {note_prefix} {diag.note}")

    return "\n".join(lines)
