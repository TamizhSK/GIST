"""GITHUB_ENV / GITHUB_OUTPUT / GITHUB_PATH / GITHUB_STEP_SUMMARY read-back.

Every `run:` step is a separate process, so nothing a step exports survives it
(trap #7). GitHub's answer is a set of files: the step appends to them, the
runner reads them back afterwards and folds the result into the next step's
environment. Replicating that exactly is what makes real-world actions work.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import re
from pathlib import Path

ENV = "env"
OUTPUT = "output"
PATH = "path"
SUMMARY = "summary"
STATE = "state"

FILES: dict[str, str] = {
    ENV: "github_env",
    OUTPUT: "github_output",
    PATH: "github_path",
    SUMMARY: "github_step_summary",
    STATE: "github_state",
}

ENV_VARS: dict[str, str] = {
    ENV: "GITHUB_ENV",
    OUTPUT: "GITHUB_OUTPUT",
    PATH: "GITHUB_PATH",
    SUMMARY: "GITHUB_STEP_SUMMARY",
    STATE: "GITHUB_STATE",
}

YEET_ALIASES: dict[str, str] = {key: f"YEET_{name[7:]}" for key, name in ENV_VARS.items()}
"""GITHUB_ENV -> YEET_ENV and so on. Both names point at the same file, so a
flow can be written in our dialect without giving up compatibility."""

_HEREDOC = re.compile(r"^(?P<key>[^=<]+)<<(?P<delim>\S+)\s*$")
"""`KEY<<EOF` — the multiline form. Actions that write a JSON blob or a PEM key
into $GITHUB_ENV use it, and a naive `KEY=value` parser mangles them silently."""


def paths_for(step_dir: Path) -> dict[str, Path]:
    """The five file paths for one step. Does not touch the disk."""
    return {key: step_dir / name for key, name in FILES.items()}


def prepare(step_dir: Path) -> dict[str, Path]:
    """Create the step directory and the five (empty) files.

    They must exist before the step runs: `echo x >> $GITHUB_ENV` works on a
    missing file, but `cat $GITHUB_ENV` in a user's script does not, and the
    difference is the kind of thing that gets reported as our bug.
    """
    step_dir.mkdir(parents=True, exist_ok=True)
    files = paths_for(step_dir)
    for path in files.values():
        path.touch()
    return files


def read_back(step_dir: Path) -> dict[str, dict[str, str]]:
    """Each step is a NEW PROCESS. This file dance is the only way state survives.

    Returns `{"env": {...}, "output": {...}, "state": {...}, "path": {...},
    "summary": {"text": ...}}`. `path` is keyed by index so ordering survives a
    dict round-trip — PATH is prepended in the order the step wrote it.

    A malformed line is skipped, never fatal: half a step's outputs is worth
    more than crashing the run over a stray line of output.
    """
    files = paths_for(step_dir)
    return {
        ENV: _parse_pairs(files[ENV]),
        OUTPUT: _parse_pairs(files[OUTPUT]),
        STATE: _parse_pairs(files[STATE]),
        PATH: {str(i): line for i, line in enumerate(_parse_lines(files[PATH]))},
        SUMMARY: {"text": _read(files[SUMMARY])},
    }


def path_entries(back: dict[str, dict[str, str]]) -> list[str]:
    """Pull `read_back()`'s PATH section back out in write order."""
    entries = back.get(PATH, {})
    return [entries[key] for key in sorted(entries, key=int)]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_lines(path: Path) -> list[str]:
    return [line.strip() for line in _read(path).splitlines() if line.strip()]


def _parse_pairs(path: Path) -> dict[str, str]:
    """`KEY=value` per line, plus the `KEY<<DELIM ... DELIM` heredoc form."""
    result: dict[str, str] = {}
    lines = _read(path).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip():
            continue

        heredoc = _HEREDOC.match(line)
        if heredoc:
            key = heredoc.group("key").strip()
            delim = heredoc.group("delim")
            body: list[str] = []
            while index < len(lines) and lines[index].strip() != delim:
                body.append(lines[index])
                index += 1
            index += 1  # consume the closing delimiter
            if key:
                result[key] = "\n".join(body)
            continue

        key, eq, value = line.partition("=")
        if eq and key.strip():
            result[key.strip()] = value
    return result
