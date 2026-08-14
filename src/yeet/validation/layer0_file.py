"""File & encoding: empty, non-UTF8, BOM, TAB indentation, CRLF, absurd size.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import re
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity

MAX_BYTES = 1_000_000


def check(path: Path) -> DiagnosticBag:
    """E001 E002 E003 W004 E005 W006 W007."""
    bag = DiagnosticBag()

    if not path.is_file():
        bag.add(
            Diagnostic(
                code="YEET-E001",
                severity=Severity.ERROR,
                message=f"File not found or unreadable: {path}",
                file=path,
            )
        )
        return bag

    try:
        raw_bytes = path.read_bytes()
    except Exception as exc:
        bag.add(
            Diagnostic(
                code="YEET-E001",
                severity=Severity.ERROR,
                message=f"Cannot read file: {exc}",
                file=path,
            )
        )
        return bag

    if len(raw_bytes) == 0:
        bag.add(
            Diagnostic(
                code="YEET-E002",
                severity=Severity.ERROR,
                message="File is empty",
                file=path,
                pos=Position(line=0, col=0),
            )
        )
        return bag

    if len(raw_bytes) > MAX_BYTES:
        bag.add(
            Diagnostic(
                code="YEET-W007",
                severity=Severity.WARNING,
                message=f"File size ({len(raw_bytes)} bytes) exceeds max limit (1 MB)",
                file=path,
            )
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        bad_offset = exc.start
        preceding = raw_bytes[:bad_offset].decode("utf-8", errors="ignore")
        preceding_lines = preceding.splitlines()
        line_no = max(0, len(preceding_lines) - 1)
        col_no = len(preceding_lines[-1]) if preceding_lines else 0

        bag.add(
            Diagnostic(
                code="YEET-E003",
                severity=Severity.ERROR,
                message=f"Non-UTF-8 character at byte offset {bad_offset}: {exc.reason}",
                file=path,
                pos=Position(line=line_no, col=col_no),
            )
        )
        return bag

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        bag.add(
            Diagnostic(
                code="YEET-W004",
                severity=Severity.WARNING,
                message="UTF-8 Byte Order Mark (BOM) present at start of file",
                file=path,
                pos=Position(line=0, col=0),
                help="Re-save file as UTF-8 without BOM",
            )
        )

    if b"\r\n" in raw_bytes:
        bag.add(
            Diagnostic(
                code="YEET-W006",
                severity=Severity.WARNING,
                message="CRLF (Windows) line endings detected",
                file=path,
                pos=Position(line=0, col=0),
                help="Convert line endings to LF (Unix style)",
            )
        )

    tab_pattern = re.compile(r"^\s*\t+")
    lines = text.splitlines()
    for line_idx, line_str in enumerate(lines):
        if tab_pattern.match(line_str):
            bag.add(
                Diagnostic(
                    code="YEET-E005",
                    severity=Severity.ERROR,
                    message="Tab character used for indentation (YAML requires spaces)",
                    file=path,
                    pos=Position(line=line_idx, col=0),
                    help="Replace tabs with spaces",
                )
            )

    return bag
