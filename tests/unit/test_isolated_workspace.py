"""`yeet run --clean` — the empty workspace GitHub gives every job.

The flag existed for a session and did nothing. `runner.py` built the isolated
directory and handed it to `JobContext.workspace`, and NEITHER backend read the
field: both used their own `self.root` for the bind mount, for
`GITHUB_WORKSPACE` and for the step loop. So `--clean` created an empty
directory, ignored it, and ran against the working tree exactly as before —
the tenth instance in this repo of a finished thing with no call site, and the
one that mattered most because the flag's whole purpose is fidelity.

What is pinned here is that the field is READ, that the two spellings of the
workspace agree, and that `actions/checkout` fills the directory instead of
announcing that it is already the repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from yeet.core.builtins import BuiltinContext
from yeet.executor.paths import CONTAINER_JOB_DIR, to_mounted_path
from yeet.storage.builtin import run_builtin


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository, because checkout is real git."""
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "t")
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "one")
    return root


# --- the layout -------------------------------------------------------------


def test_the_isolated_workspace_is_per_job(tmp_path):
    """Two legs of a matrix must not write into one checkout, as on GitHub."""
    from yeet.executor.workspace import create

    layout = create(tmp_path, "run-1")
    one = layout.job("test (node 18)").isolated_workspace
    two = layout.job("test (node 20)").isolated_workspace

    assert one != two
    assert one.parent != two.parent


def test_step_scripts_map_into_their_own_mount(tmp_path):
    """The scratch dir is outside an isolated workspace, so it needs a mount.

    Without the second bind the container is handed a script path that does not
    exist inside it, and the step dies on `no such file` naming a path the user
    can see perfectly well on the host.
    """
    job_dir = tmp_path / ".yeet" / "tmp" / "run-1" / "build"
    script = job_dir / "step-0" / "script.sh"
    script.parent.mkdir(parents=True)
    script.touch()

    assert (
        to_mounted_path(script, job_dir, CONTAINER_JOB_DIR)
        == f"{CONTAINER_JOB_DIR}/step-0/script.sh"
    )


def test_a_backend_reads_the_workspace_it_was_given(tmp_path, repo):
    """The regression that started this: `ctx.workspace` had no reader.

    Driven through LocalBackend because it needs no daemon — the assertion is
    about the step loop's configuration, which both backends build the same way.
    """
    from conftest import make_instance, make_job, make_step

    from yeet.core.result import Status
    from yeet.executor.backend import JobContext
    from yeet.executor.local_backend import LocalBackend

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "only-here.txt").write_text("yes\n", encoding="utf-8")

    job = make_job("build", [make_step("cat only-here.txt")])
    result = LocalBackend(repo).run_job(make_instance(job), JobContext(workspace=elsewhere))

    assert result.status is Status.SUCCESS, (
        "the step ran in the project root, not in the workspace it was handed"
    )


# --- checkout ---------------------------------------------------------------


def test_checkout_fills_an_isolated_workspace(tmp_path, repo):
    """The lie this replaces: "the workspace is already this repository",
    printed over an empty directory, after which every step ran against
    nothing."""
    empty = tmp_path / "job-workspace"
    empty.mkdir()
    lines: list[str] = []

    result = run_builtin(
        "actions/checkout",
        BuiltinContext(
            root=repo,
            run_id="run-1",
            workspace=empty,
            isolated=True,
            inputs={},
            emit=lines.append,
        ),
    )

    assert result.ok, result.message
    assert (empty / "main.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert not any("already this repository" in line for line in lines), lines
    assert result.outputs["commit"], "checkout must report the SHA it placed"


def test_checkout_into_an_isolated_workspace_needs_no_path(tmp_path, repo):
    """The refusal protects a WORKING TREE. An isolated workspace is ours, and
    filling its root is the entire point of the mode."""
    empty = tmp_path / "job-workspace"
    empty.mkdir()

    result = run_builtin(
        "actions/checkout",
        BuiltinContext(
            root=repo,
            run_id="run-1",
            workspace=empty,
            isolated=True,
            inputs={"ref": "HEAD"},
            emit=lambda _: None,
        ),
    )

    assert result.ok, result.message


def test_checkout_still_refuses_to_overwrite_a_working_tree(repo):
    """The bind-mounted case is unchanged, and that is the important half."""
    result = run_builtin(
        "actions/checkout",
        BuiltinContext(
            root=repo,
            run_id="run-1",
            workspace=repo,
            isolated=False,
            inputs={"ref": "v1.2.3"},
            emit=lambda _: None,
        ),
    )

    assert not result.ok
    assert "path:" in result.message


def test_the_default_checkout_reports_the_commit_it_is_standing_on(repo):
    """`steps.<id>.outputs.commit` must not be empty just because there was
    nothing to fetch — the commit is right there in the repo."""
    result = run_builtin(
        "actions/checkout",
        BuiltinContext(root=repo, run_id="run-1", workspace=repo, inputs={}, emit=lambda _: None),
    )

    assert result.ok
    assert len(result.outputs["commit"]) == 40, result.outputs


# --- the two spellings of one fact ------------------------------------------


def test_github_workspace_is_per_job_and_not_shared(tmp_path):
    """`for_instance` copies shallowly, so the github dict is SHARED between
    every leg in the pool. Writing the workspace into it would give them all
    whichever job was assigned last — the same hazard `matrix` is snapshotted
    for."""
    from yeet.executor.runner import _with_workspace
    from yeet.expressions.contexts import Contexts

    base = Contexts(github={"run_id": "r1", "workspace": "/original"})

    one = _with_workspace(base, tmp_path / "a")
    two = _with_workspace(base, tmp_path / "b")

    assert one is not None and two is not None
    assert one.github["workspace"] == str(tmp_path / "a")
    assert two.github["workspace"] == str(tmp_path / "b")
    assert base.github["workspace"] == "/original", "the shared dict was mutated"
    assert one.github["run_id"] == "r1", "the rest of the context must survive"
