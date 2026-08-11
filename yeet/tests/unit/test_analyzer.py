"""A3, A5, A6, A7 — root detection, discovery, fingerprinting, analyze().

Fixture trees are built under tmp_path exactly as the plan's "Done when"
lists them: git repo vs bare dir vs nested subdir vs $HOME boundary; monorepo
with node_modules, symlink loop, unreadable dir; fingerprinting this-style
Python repo and a Node repo.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yeet.analyzer.discover import MAX_DEPTH, discover
from yeet.analyzer.fingerprint import fingerprint
from yeet.analyzer.markers import EXTENSION_MARKERS, MARKERS
from yeet.analyzer.project import analyze
from yeet.analyzer.root import find_root


def _touch(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# --- A3: find_root ----------------------------------------------------------


def test_a3_git_repo_wins(tmp_path):
    repo = tmp_path / "repo"
    _touch(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    deep = repo / "src" / "app" / "deep"
    _touch(deep / "file.py")

    assert find_root(deep) == repo.resolve()


def test_a3_bare_dir_resolves_to_itself(tmp_path):
    bare = tmp_path / "fresh"
    bare.mkdir()

    assert find_root(bare) == bare.resolve()


def test_a3_nested_subdir_in_marker_tree(tmp_path):
    repo = tmp_path / "proj"
    _touch(repo / "package.json", '{"name": "x"}')
    nested = repo / "a" / "b"
    _touch(nested / "index.js")

    assert find_root(nested) == repo.resolve()


def test_a3_stops_at_home_boundary(tmp_path, monkeypatch):
    home = tmp_path / "home"
    sub = home / "sub"
    _touch(sub / "file.txt")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home.resolve()))

    assert find_root(sub) == sub.resolve()


def test_a3_home_marker_is_found_from_below(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _touch(home / ".git" / "HEAD", "ref: refs/heads/main\n")
    sub = home / "sub"
    _touch(sub / "file.txt")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home.resolve()))

    assert find_root(sub) == home.resolve()


# --- A4: markers table ------------------------------------------------------


def test_a4_markers_table_is_complete():
    assert len(MARKERS) == 16, "markers table must be fully filled in"
    assert EXTENSION_MARKERS, "extension markers must be populated"
    assert "package.json" in MARKERS
    assert "pyproject.toml" in MARKERS
    assert ".csproj" in EXTENSION_MARKERS


# --- A5: discover -----------------------------------------------------------


def test_a5_monorepo_excludes_node_modules(tmp_path):
    root = tmp_path / "mono"
    _touch(root / ".yeet" / "flows" / "main.yml", "on: push\njobs: {}\n")
    _touch(root / "app" / "node_modules" / "pkg" / ".github" / "workflows" / "hidden.yml")
    _touch(root / "app" / "node_modules" / "pkg" / "yeet.yml")

    found = discover(root)
    flows, foreign = found.flows, found.foreign_ci
    assert [f.relative_to(root) for f in flows] == [Path(".yeet/flows/main.yml")]
    assert foreign == []


def test_a5_precedence_yeet_then_github_then_root(tmp_path):
    root = tmp_path / "prec"
    _touch(root / "yeet.yml", "on: push\n")
    _touch(root / ".github" / "workflows" / "ci.yml", "on: push\n")
    _touch(root / ".yeet" / "flows" / "main.yml", "on: push\n")

    found = discover(root)
    flows = found.flows
    assert [f.relative_to(root) for f in flows] == [
        Path(".yeet/flows/main.yml"),
        Path(".github/workflows/ci.yml"),
        Path("yeet.yml"),
    ]


def test_a5_foreign_ci_reported_not_parsed(tmp_path):
    root = tmp_path / "foreign"
    _touch(root / ".gitlab-ci.yml", "image: alpine\n")
    _touch(root / "Jenkinsfile", "pipeline {}\n")

    found = discover(root)
    flows, foreign = found.flows, found.foreign_ci
    assert flows == []
    assert {f.name for f in foreign} == {".gitlab-ci.yml", "Jenkinsfile"}


def test_a5_depth_and_ignore_are_honoured(tmp_path):
    root = tmp_path / "depth"
    _touch(root / ".yeet" / "flows" / "main.yml")
    _touch(root / "a" / "b" / "c" / "d" / "e" / ".github" / "workflows" / "too_deep.yml")
    _touch(root / ".yeetignore", ".yeet/tmp\n")

    found = discover(root)
    flows = found.flows
    rels = [f.relative_to(root) for f in flows]
    assert Path(".yeet/flows/main.yml") in rels
    assert len(rels) == 1, f"expected only the top flow, got {rels}"


def test_a5_unreadable_dir_does_not_raise(tmp_path, monkeypatch):
    root = tmp_path / "locked"
    _touch(root / ".yeet" / "flows" / "main.yml")
    locked = root / "secret"
    _touch(locked / "inaccessible.yml")

    real_scandir = os.scandir

    def guarded_scandir(path):
        if os.fspath(path).endswith("secret"):
            raise PermissionError(13, "access denied")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", guarded_scandir)

    flows = discover(root).flows  # must not raise, must not hang
    assert [f.relative_to(root) for f in flows] == [Path(".yeet/flows/main.yml")]


def test_a5_symlink_loop_never_hangs(tmp_path):
    root = tmp_path / "loop"
    root.mkdir()
    try:
        os.symlink(root, root / "self")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privilege on this platform")

    found = discover(root)
    flows = found.flows
    assert flows == []


def test_a5_truncation_flag(tmp_path, monkeypatch):
    import yeet.analyzer.discover as discover_mod

    root = tmp_path / "big"
    _touch(root / ".yeet" / "flows" / "main.yml")
    for i in range(5):
        _touch(root / f"f{i}.txt")
    monkeypatch.setattr(discover_mod, "MAX_FILES", 3)

    result = discover_mod.discover(root)
    assert result.truncated is True


# --- A6: fingerprint --------------------------------------------------------


def test_a6_node_repo_reads_engines(tmp_path):
    root = tmp_path / "nodeapp"
    _touch(root / "package.json", '{"engines": {"node": ">=18.20"}}')

    ecos = fingerprint(root)
    assert len(ecos) == 1
    assert ecos[0].name == "node"
    assert ecos[0].version == "18"
    assert ecos[0].suggested_image == "node:18"


def test_a6_python_repo_reads_requires_python(tmp_path):
    root = tmp_path / "pyapp"
    _touch(root / "pyproject.toml", '[project]\nrequires-python = ">=3.11"\n')

    ecos = fingerprint(root)
    assert len(ecos) == 1
    assert ecos[0].name == "python"
    assert ecos[0].version == "3.11"
    assert ecos[0].suggested_image == "python:3.11"


def test_a6_polyglot_returns_all(tmp_path):
    root = tmp_path / "poly"
    _touch(root / "package.json", "{}")
    _touch(root / "pyproject.toml", "[project]\n")

    names = sorted(e.name for e in fingerprint(root))
    assert names == ["node", "python"]


def test_a6_dockerfile_is_infra_not_ecosystem(tmp_path):
    root = tmp_path / "infra"
    _touch(root / "Dockerfile", "FROM alpine\n")

    assert fingerprint(root) == []


# --- A7: analyze() ---------------------------------------------------------


def test_a7_populates_project(tmp_path):
    root = tmp_path / "proj"
    _touch(root / ".git" / "HEAD", "ref: refs/heads/feature-x\n")
    _touch(root / ".yeet" / "flows" / "main.yml", "on: push\n")
    _touch(root / "package.json", '{"engines": {"node": ">=20"}}')
    _touch(root / "Dockerfile", "FROM node:20\n")
    _touch(root / ".gitlab-ci.yml", "image: alpine\n")

    project = analyze(root / "src")

    assert project.root == root.resolve()
    assert project.is_git is True
    assert project.branch == "feature-x"
    assert project.flows == [root.resolve() / ".yeet" / "flows" / "main.yml"]
    assert [f.name for f in project.foreign_ci] == [".gitlab-ci.yml"]
    assert project.ecosystems[0].name == "node"
    assert project.dockerfile is not None
    assert project.has_flows is True
    assert "node" in project.stack


def test_a7_bare_dir_is_project_without_git(tmp_path):
    root = tmp_path / "bareproj"
    _touch(root / "yeet.yml", "on: push\n")

    project = analyze(root)
    assert project.root == root.resolve()
    assert project.is_git is False
    assert project.branch is None
    assert len(project.flows) == 1
    assert project.dockerfile is None


def test_a7_max_depth_constant_is_5():
    assert MAX_DEPTH == 5
