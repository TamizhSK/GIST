"""Bind mount, /workspace layout, temp script dir.

Everything a run writes lives under `.yeet/tmp/<run-id>/`, which is inside the
project root on purpose: the root is what gets bind-mounted at `/workspace`, so
a step script written here is visible to the container without a second mount.

`.yeet/tmp/` is already in `.gitignore`, and discovery excludes it — a run that
writes files must not look like a project change.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from yeet.executor.paths import to_workspace_path

TMP_DIR = Path(".yeet") / "tmp"
RUNS_DIR = Path(".yeet") / "runs"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def new_run_id() -> str:
    """Sortable and unique: `20260811-142309-3f8a`.

    Sortable matters because `yeet logs` with no argument means "the last run",
    and sorting directory names is cheaper and more reliable than stat'ing them.
    """
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def slug(text: str) -> str:
    """`build (node 20)` -> `build-node-20`. Stable across runs.

    Job keys carry matrix legs and therefore spaces, parentheses and commas.
    Those are legal in a job key, hostile in a path, and outright broken in a
    container path on Windows.

    Leading and trailing dots go too. A job key of `..` is legal YAML and would
    otherwise produce a directory name that escapes the run directory — the
    kind of thing that is only funny until someone's `cleanup()` runs.
    """
    cleaned = _UNSAFE.sub("-", text).strip("-.").lower()
    return cleaned or "job"


@dataclass(frozen=True, slots=True)
class StepLayout:
    """Where one step's script and its five state files live."""

    index: int
    dir: Path
    script: Path

    def container_script(self, root: Path) -> str:
        return to_workspace_path(self.script, root)


@dataclass(frozen=True, slots=True)
class JobLayout:
    """`.yeet/tmp/<run-id>/<job-slug>/`."""

    root: Path
    run_id: str
    job_key: str
    dir: Path

    @property
    def isolated_workspace(self) -> Path:
        """A private, empty workspace for this job — `yeet run --clean`.

        GitHub hands a job an EMPTY directory and `actions/checkout` fills it.
        Bind-mounting the user's working tree is the right default for a local
        runner (you want to test what you are editing), but it hides two whole
        classes of bug: a workflow with no `checkout` step at all, and one that
        passes only because of a file you have not committed. This directory is
        where the faithful version runs.

        Per JOB, not per run: two jobs of a matrix must not write into one
        checkout, exactly as they do not on GitHub.
        """
        return self.dir / "workspace"

    def step(self, index: int, suffix: str = ".sh") -> StepLayout:
        step_dir = self.dir / f"step-{index}"
        step_dir.mkdir(parents=True, exist_ok=True)
        return StepLayout(index=index, dir=step_dir, script=step_dir / f"script{suffix}")


@dataclass(frozen=True, slots=True)
class RunLayout:
    """`.yeet/tmp/<run-id>/` plus the log directory for this run."""

    root: Path
    run_id: str

    @property
    def dir(self) -> Path:
        return self.root / TMP_DIR / self.run_id

    @property
    def logs_dir(self) -> Path:
        """Dev D's `storage.runs.RunStore` writes JSONL here. We only name it —
        the executor never writes logs itself (it emits to a LogSink)."""
        return self.root / RUNS_DIR / self.run_id

    def job(self, job_key: str) -> JobLayout:
        job_dir = self.dir / slug(job_key)
        job_dir.mkdir(parents=True, exist_ok=True)
        return JobLayout(root=self.root, run_id=self.run_id, job_key=job_key, dir=job_dir)

    def cleanup(self) -> None:
        """Remove this run's scratch dir. Never raises — cleanup failing must
        not turn a green run red."""
        shutil.rmtree(self.dir, ignore_errors=True)


def create(root: Path, run_id: str | None = None) -> RunLayout:
    layout = RunLayout(root=root, run_id=run_id or new_run_id())
    layout.dir.mkdir(parents=True, exist_ok=True)
    return layout


def prune_tmp(root: Path) -> int:
    """Delete every run's scratch directory. Returns how many were removed."""
    tmp = root / TMP_DIR
    if not tmp.is_dir():
        return 0
    removed = 0
    for entry in tmp.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed
