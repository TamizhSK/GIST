"""Run a command under a real pty and render what a terminal would show.

WHY THIS FILE EXISTS. A progress bar is written with carriage returns, so the
bytes on the wire and the pixels on the screen are different things: forty
frames of `\\r`-overwritten text are ONE line to a person and forty lines to
anything that splits on newlines. Asserting on the raw stream tests the wrong
object.

THE BUG THIS PREVENTS, which cost a review cycle: the capture was read back
with `open(path)`. Python's universal-newline translation turns every lone
`\\r` into `\\n` on read, so a single in-place bar became fifty-eight separate
lines, and a screen with one bar on it "proved" there were fifty-eight. The
reader below opens in binary and decodes explicitly. There is no configuration
in which text mode is correct here.

The emulator handles the three sequences a bar uses — `\\r`, `\\n`, and
`ESC[K` — and drops SGR colour, which is what the assertions want. It is not a
terminal; it is exactly enough of one to answer "what is on the screen".
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import termios
import time

__all__ = ["capture", "render", "bar_lines"]

_SGR = re.compile(r"\x1b\[[0-9;]*m")
_ERASE_TO_EOL = "\x1b[K"


def capture(
    argv: list[str],
    *,
    cols: int = 100,
    rows: int = 40,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
    cwd: str | None = None,
) -> str:
    """Run `argv` attached to a pty of exactly `cols`x`rows`; return its output.

    The window size is set on the SLAVE FD BEFORE the child is spawned. Setting
    it afterwards is a race the child usually wins: it has already asked how
    wide the terminal is, got the default, and drawn to that.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    child_env = dict(os.environ, TERM="xterm-256color", LANG="en_US.UTF-8")
    child_env.pop("COLUMNS", None)  # or it wins over the real window size
    child_env.update(env or {})

    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, env=child_env, cwd=cwd)
    os.close(slave)
    chunks: list[bytes] = []
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:  # the child closed its end
                    break
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                break
    finally:
        os.close(master)
        proc.wait(timeout=10)
    # Binary in, explicit decode out. Never text mode — see the module docstring.
    return b"".join(chunks).decode("utf-8", "replace")


def render(stream: str) -> list[str]:
    """The lines a terminal would be showing after `stream`, colour removed."""
    rows: list[str] = [""]
    row = col = 0

    def ensure(n: int) -> None:
        while len(rows) <= n:
            rows.append("")

    i = 0
    while i < len(stream):
        if stream.startswith(_ERASE_TO_EOL, i):
            ensure(row)
            rows[row] = rows[row][:col]
            i += len(_ERASE_TO_EOL)
            continue
        match = _SGR.match(stream, i)
        if match:
            i = match.end()
            continue
        ch = stream[i]
        i += 1
        if ch == "\r":
            col = 0
            continue
        if ch == "\n":
            row += 1
            col = 0
            ensure(row)
            continue
        ensure(row)
        line = rows[row]
        if len(line) < col:
            line += " " * (col - len(line))
        rows[row] = line[:col] + ch + line[col + 1 :]
        col += 1
    return rows


def bar_lines(rows: list[str]) -> list[str]:
    """The rows that are a progress bar, in either alphabet."""
    return [r for r in rows if "%" in r and ("█" in r or "░" in r or "#" in r or "-" in r)]
