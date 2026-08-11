"""JSONL run logs under .yeet/runs/<run-id>/. Powers `yeet logs`.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from yeet.core.events import LogEvent, LogSink


class RunStore(LogSink):
    """Persists LogEvent stream as JSONL under `.yeet/runs/<run_id>/log.jsonl`."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.run_dir = root / ".yeet" / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.run_dir / "log.jsonl"

    def emit(self, event: LogEvent) -> None:
        record = {
            "ts": event.ts,
            "job": event.job,
            "step": event.step,
            "stream": event.stream,
            "text": event.text,
        }
        try:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass


def get_latest_run_id(root: Path) -> str | None:
    """Find the most recent run ID under `.yeet/runs/`."""
    runs_dir = root / ".yeet" / "runs"
    if not runs_dir.exists():
        return None
    dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not dirs:
        return None
    latest = max(dirs, key=lambda d: d.stat().st_mtime)
    return latest.name


def replay(root: Path, run_id: str | None = None) -> Iterator[LogEvent]:
    """Replay log events from `.yeet/runs/<run-id>/log.jsonl`."""
    target_id = run_id or get_latest_run_id(root)
    if not target_id:
        return

    log_file = root / ".yeet" / "runs" / target_id / "log.jsonl"
    if not log_file.exists():
        return

    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield LogEvent(
                    ts=float(data.get("ts", 0.0)),
                    job=str(data.get("job", "")),
                    step=str(data.get("step", "")),
                    stream=str(data.get("stream", "stdout")),
                    text=str(data.get("text", "")),
                )
            except Exception:
                continue
