"""yeet under a git hook, cron, or Task Scheduler — where $HOME is not set.

The environment a hook runs in is not the one the user's shell has. `git
commit` strips it, cron never sourced an rc file, and Task Scheduler runs as a
service account. `Path.home()` does not return a guess in that situation, it
RAISES, and two modules walked upward using it as their stopping point — so
`yeet scan` from a hook ended in a traceback rather than a result.

Found by the Windows CI leg, which builds its subprocess env by hand and
therefore hit the same condition by accident.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from yeet.analyzer.root import find_root
from yeet.expressions import contexts

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def no_home(monkeypatch):
    """`Path.home()` as it behaves when the environment does not say."""

    def raises() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", staticmethod(raises))


def test_find_root_walks_up_without_a_home(tmp_path, no_home):
    project = tmp_path / "proj"
    (project / ".git").mkdir(parents=True)
    (project / "src").mkdir()

    assert find_root(project / "src") == project.resolve()


def test_find_root_still_answers_when_nothing_marks_a_root(tmp_path, no_home):
    """No marker anywhere and no home to stop at. The walk has to end at the
    filesystem root and hand back something usable, not loop or raise."""
    plain = tmp_path / "plain"
    plain.mkdir()

    assert find_root(plain) == plain.resolve()


def test_the_git_dir_lookup_survives_it_too(tmp_path, no_home):
    """The second copy of the same walk. It used home as its stop condition
    for the same reason and broke in the same place."""
    project = tmp_path / "proj"
    (project / ".git").mkdir(parents=True)

    assert contexts._find_git_dir(project) == (project / ".git").resolve()


def _minimal_env() -> dict[str, str]:
    """PATH only — plus what the OS itself cannot start Python without.

    `SystemRoot` is not optional on Windows: without it the interpreter cannot
    seed hash randomisation and dies before `main()`. That is the OS's floor,
    not ours, and a hook always has it.
    """
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")}
    if sys.platform == "win32":
        for name in ("SystemRoot", "SYSTEMROOT", "COMSPEC", "PATHEXT"):
            if name in os.environ:
                env[name] = os.environ[name]
    return env


@pytest.mark.parametrize("args", [("--version",), ("scan", "tests/fixtures/sample_project")])
def test_the_cli_runs_with_no_home_in_the_environment(tmp_path, args):
    """The end-to-end shape of the same thing: `env -i PATH=... yeet ...`."""
    done = subprocess.run(
        [sys.executable, "-m", "yeet", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_minimal_env(),
        timeout=120,
        check=False,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "Traceback" not in done.stdout + done.stderr
