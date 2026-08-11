"""B5 — build_github_context. Fake `.git` trees under tmp_path; no git binary."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from yeet.expressions.contexts import build_github_context

SHA = "a" * 40
SHA2 = "b" * 40


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_repo(tmp_path, *, head="ref: refs/heads/main", sha=SHA, config=None):
    root = tmp_path / "proj"
    write(root / ".git" / "HEAD", head + "\n")
    if sha and head.startswith("ref:") and " refs/heads/" in head:
        write(root / ".git" / head.split(":")[1].strip(), sha + "\n")
    if config is not None:
        write(root / ".git" / "config", config)
    return root


def test_basic_repo(tmp_path):
    root = make_repo(
        tmp_path,
        config='[remote "origin"]\n\turl = git@github.com:me/proj.git\n',
    )
    ctx = build_github_context(root, "push")
    assert ctx["sha"] == SHA
    assert ctx["ref"] == "refs/heads/main"
    assert ctx["ref_name"] == "main"
    assert ctx["repository"] == "me/proj"


def test_non_git_directory_degrades_gracefully(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    ctx = build_github_context(root, "push")
    assert ctx["workspace"] == str(root)
    assert ctx["event_name"] == "push"
    for key in ("sha", "ref", "ref_name", "repository"):
        assert key not in ctx


def test_detached_head(tmp_path):
    root = make_repo(tmp_path, head=SHA)
    ctx = build_github_context(root, "push")
    assert ctx["sha"] == SHA
    assert "ref" not in ctx
    assert "ref_name" not in ctx


def test_tag_ref(tmp_path):
    root = make_repo(tmp_path, head="ref: refs/tags/v1.0", sha=SHA)
    ctx = build_github_context(root, "push")
    assert ctx["ref"] == "refs/tags/v1.0"
    assert ctx["ref_name"] == "v1.0"


def test_sha_read_from_packed_refs(tmp_path):
    root = make_repo(tmp_path, head="ref: refs/heads/main", sha=None)
    write(root / ".git" / "packed-refs", f"# pack-refs\n{SHA} refs/heads/main\n")
    ctx = build_github_context(root, "push")
    assert ctx["sha"] == SHA


def test_https_origin(tmp_path):
    root = make_repo(tmp_path, config='[remote "origin"]\n\turl = https://github.com/me/proj\n')
    ctx = build_github_context(root, "push")
    assert ctx["repository"] == "me/proj"


def test_unknown_remote_still_yields_last_two_segments(tmp_path):
    root = make_repo(tmp_path, config='[remote "origin"]\n\turl = git@gitlab.local:team/app.git\n')
    ctx = build_github_context(root, "push")
    assert ctx["repository"] == "team/app"


def test_repo_root_found_by_walking_up(tmp_path):
    config = '[remote "origin"]\n\turl = git@github.com:me/proj.git\n'
    repo_root = make_repo(tmp_path, config=config)
    nested = repo_root / "a" / "b"
    nested.mkdir(parents=True)
    ctx = build_github_context(nested, "push")
    assert ctx["sha"] == SHA


def test_worktree_gitdir_file(tmp_path):
    main = tmp_path / "main"
    write(main / ".git" / "HEAD", "ref: refs/heads/feature\n")
    write(main / ".git" / "refs/heads/feature", SHA + "\n")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    write(worktree / ".git", f"gitdir: {main / '.git'}\n")
    ctx = build_github_context(worktree, "push")
    assert ctx["sha"] == SHA
    assert ctx["ref_name"] == "feature"


def test_actor_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTOR", "octocat")
    ctx = build_github_context(tmp_path / "bare", "push")
    assert ctx["actor"] == "octocat"


def test_run_id_prefers_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "7")
    ctx = build_github_context(tmp_path / "bare", "push")
    assert ctx["run_id"] == "12345"
    assert ctx["run_number"] == 7


def test_run_id_fallback_shape(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)
    ctx = build_github_context(tmp_path / "bare", "push")
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", ctx["run_id"])
    assert ctx["run_number"] == 1


def test_missing_git_dir_inside_home_is_ignored(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    write(home / ".git" / "HEAD", "ref: refs/heads/personal\n")
    write(home / ".git" / "refs/heads/personal", SHA2 + "\n")
    project = home / "projects" / "app"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    ctx = build_github_context(project, "push")
    assert "sha" not in ctx


def test_run_number_defaults_when_env_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "")
    ctx = build_github_context(tmp_path / "bare", "push")
    assert ctx["run_number"] == 1


def test_workspace_is_resolved_absolute_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    ctx = build_github_context(root, "push")
    assert ctx["workspace"] == str(root.resolve())


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:me/proj.git", "me/proj"),
        ("git@github.com:me/proj", "me/proj"),
        ("https://github.com/me/proj.git", "me/proj"),
        ("ssh://git@github.com/me/proj", "me/proj"),
        ("git://github.com/me/proj", "me/proj"),
    ],
)
def test_owner_repo_parsing(tmp_path, url, expected):
    root = make_repo(tmp_path, config=f'[remote "origin"]\n\turl = {url}\n')
    ctx = build_github_context(root, "push")
    assert ctx["repository"] == expected
