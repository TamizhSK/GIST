"""The base_env decision — the spec gap executor/env.py fills."""

from __future__ import annotations

from pathlib import Path

from yeet.executor import env as env_mod
from yeet.executor import state_files


def test_base_env_has_the_variables_tooling_expects():
    env = env_mod.base_env(workspace="/workspace", run_id="r1", job_key="build")
    assert env["CI"] == "true"
    assert env["GITHUB_ACTIONS"] == "true"
    assert env["YEET"] == "true"
    assert env["GITHUB_WORKSPACE"] == "/workspace"
    assert env["GITHUB_JOB"] == "build"
    assert env["GITHUB_RUN_ID"] == "r1"
    assert "RUNNER_OS" in env
    assert "RUNNER_ARCH" in env


def test_container_env_always_reports_linux(monkeypatch):
    """The image is Linux whatever the host is — telling a step otherwise sends
    it looking for `brew` inside Ubuntu."""
    monkeypatch.setattr(env_mod, "runner_os", lambda: "macOS")
    env = env_mod.container_base_env(run_id="r1", job_key="build", event="push")
    assert env["RUNNER_OS"] == "Linux"
    assert env["GITHUB_WORKSPACE"] == "/workspace"


def test_github_context_maps_to_env():
    env = env_mod.github_env(
        {"sha": "abc123", "ref_name": "main", "repository": "me/proj", "unknown": "x"}
    )
    assert env["GITHUB_SHA"] == "abc123"
    assert env["GITHUB_REF_NAME"] == "main"
    assert env["GITHUB_REPOSITORY"] == "me/proj"
    assert "GITHUB_UNKNOWN" not in env


def test_with_becomes_input_vars():
    env = env_mod.input_env({"node-version": 20, "fetch depth": "0", "Flag": True})
    assert env["INPUT_NODE_VERSION"] == "20"
    assert env["INPUT_FETCH_DEPTH"] == "0"
    assert env["INPUT_FLAG"] == "true"


def test_yaml_scalars_become_shell_strings():
    """`True` must render as `true` — `[ "$FLAG" = "true" ]` is the normal shape."""
    env = env_mod.stringify_all({"DEBUG": True, "QUIET": False, "PORT": 8080, "NOTHING": None})
    assert env == {"DEBUG": "true", "QUIET": "false", "PORT": "8080", "NOTHING": ""}


def test_state_file_env_exports_both_names(tmp_path):
    files = state_files.prepare(tmp_path)
    env = env_mod.state_file_env(files)
    assert env["GITHUB_ENV"] == env["YEET_ENV"] == str(files["env"])
    assert env["GITHUB_STEP_SUMMARY"] == env["YEET_STEP_SUMMARY"]


def test_state_file_env_uses_the_converter(tmp_path):
    files = state_files.prepare(tmp_path)
    env = env_mod.state_file_env(files, to_path=lambda path: f"/workspace/{path.name}")
    assert env["GITHUB_OUTPUT"] == "/workspace/github_output"


def test_merge_path_prepends_in_order():
    env = {"PATH": "/usr/bin"}
    env_mod.merge_path(env, ["/opt/a", "/opt/b"])
    assert env["PATH"] == "/opt/a:/opt/b:/usr/bin"


def test_merge_path_with_no_entries_is_a_noop():
    env = {"PATH": "/usr/bin"}
    env_mod.merge_path(env, [])
    assert env["PATH"] == "/usr/bin"


def test_state_file_env_covers_every_file(tmp_path):
    files = env_mod.state_files.paths_for(Path(tmp_path))
    env = env_mod.state_file_env(files)
    assert len(env) == 2 * len(state_files.FILES)
