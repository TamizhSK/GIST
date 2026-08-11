"""C7 — the .yeet/tmp layout, and the slug that makes matrix keys path-safe."""

from __future__ import annotations

import pytest

from yeet.executor import workspace


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("build", "build"),
        ("build (node 20)", "build-node-20"),
        ("test (os: ubuntu, node: 18)", "test-os-ubuntu-node-18"),
        ("Deploy/Prod", "deploy-prod"),
        ("...", "job"),
    ],
)
def test_slug_is_path_safe_and_stable(key, expected):
    assert workspace.slug(key) == expected
    assert workspace.slug(key) == workspace.slug(key)


def test_run_ids_sort_chronologically():
    """`yeet logs` with no argument means "the last run" — sorting must work."""
    first = workspace.new_run_id()
    second = workspace.new_run_id()
    assert sorted([second, first])[-1] >= first


def test_layout_lives_under_the_project_root(tmp_path):
    layout = workspace.create(tmp_path, "run-1")
    assert layout.dir == tmp_path / ".yeet" / "tmp" / "run-1"
    assert layout.dir.is_dir()
    assert layout.logs_dir == tmp_path / ".yeet" / "runs" / "run-1"


def test_job_and_step_directories(tmp_path):
    layout = workspace.create(tmp_path, "run-1")
    job = layout.job("build (node 20)")
    assert job.dir.name == "build-node-20"

    step = job.step(1)
    assert step.dir.is_dir()
    assert step.script.name == "script.sh"


def test_step_script_has_a_container_path(tmp_path):
    layout = workspace.create(tmp_path, "run-1")
    step = layout.job("build").step(2)
    step.script.touch()
    assert step.container_script(tmp_path).startswith("/workspace/.yeet/tmp/run-1/build/step-2")


def test_custom_suffix_for_powershell(tmp_path):
    layout = workspace.create(tmp_path, "run-1")
    assert layout.job("build").step(1, ".ps1").script.name == "script.ps1"


def test_cleanup_never_raises(tmp_path):
    layout = workspace.create(tmp_path, "run-1")
    layout.cleanup()
    layout.cleanup()  # already gone
    assert not layout.dir.exists()


def test_prune_tmp_counts_runs_and_spares_logs(tmp_path):
    for run_id in ("a", "b", "c"):
        workspace.create(tmp_path, run_id)
    (tmp_path / ".yeet" / "runs").mkdir(parents=True)

    assert workspace.prune_tmp(tmp_path) == 3
    assert (tmp_path / ".yeet" / "runs").is_dir(), "run logs are not scratch"


def test_prune_tmp_on_a_clean_project(tmp_path):
    assert workspace.prune_tmp(tmp_path) == 0
