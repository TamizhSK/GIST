"""watchdog daemon. DEBOUNCE or a run's own writes retrigger it forever.

Owner: Dev D
Tier: 6 — may import from: everything below tier 6
See docs/architecture.md
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

DEBOUNCE_MS = 500
IGNORED_DIRS = {".git", "node_modules", "target", ".yeet", "__pycache__", ".venv"}


def watch_directory(target_path: Path, callback: Callable[[Path], None]) -> None:
    """Simple debounced file watcher polling loop. Ignored directories excluded."""
    last_trigger = 0.0
    last_mtimes: dict[Path, float] = {}

    print(f"Watching directory {target_path} for workflow changes (Ctrl+C to stop)...")

    while True:
        try:
            time.sleep(DEBOUNCE_MS / 1000.0)
            now = time.time()

            if now - last_trigger < (DEBOUNCE_MS / 1000.0):
                continue

            for file_path in target_path.rglob("*.yml"):
                if any(part in IGNORED_DIRS for part in file_path.parts):
                    continue

                mtime = file_path.stat().st_mtime
                prev_mtime = last_mtimes.get(file_path, 0.0)

                if mtime > prev_mtime:
                    last_mtimes[file_path] = mtime
                    if prev_mtime > 0.0:  # Skip initial scan trigger
                        last_trigger = now
                        callback(file_path)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Watcher error: {exc}")
