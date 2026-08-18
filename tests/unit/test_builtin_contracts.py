"""The built-in inputs that decide pass/fail, against `actions/*@v4`.

Every case here is one where yeet used to be GREEN and GitHub would have been
RED. That direction is the one a local runner must never get wrong: a red run
that should be green wastes an afternoon, a green run that should be red ships.

They were all the same bug — an input read from the workflow, carried through
interpolation, and then never looked at — which is the shape W317 exists to
catch in a `run:` block and nothing was catching in a `with:` block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.core.builtins import BuiltinContext
from yeet.storage import artifacts as artifacts_mod
from yeet.storage import cache as cache_mod
from yeet.storage.builtin import run_builtin


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _ctx(tmp_path: Path, workspace: Path, inputs: dict[str, object]) -> BuiltinContext:
    return BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs=inputs,
        emit=lambda line: None,
    )


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# --- upload-artifact --------------------------------------------------------


def test_if_no_files_found_error_fails_the_step(tmp_path, workspace):
    """A workflow sets this because an empty artifact means the build produced
    nothing. Ignoring it turned that assertion into a comment."""
    result = run_builtin(
        "actions/upload-artifact",
        _ctx(tmp_path, workspace, {"path": "dist/**", "if-no-files-found": "error"}),
    )

    assert not result.ok
    assert "if-no-files-found" in result.message


def test_if_no_files_found_ignore_says_nothing(tmp_path, workspace):
    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs={"path": "dist/**", "if-no-files-found": "ignore"},
        emit=lines.append,
    )

    result = run_builtin("actions/upload-artifact", ctx)

    assert result.ok
    assert not lines, lines


def test_the_default_is_still_warn(tmp_path, workspace):
    """Unchanged, and deliberately: plenty of workflows upload optional output."""
    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs={"path": "dist/**"},
        emit=lines.append,
    )

    assert run_builtin("actions/upload-artifact", ctx).ok
    assert any("no files matched" in line for line in lines)


def test_v4_refuses_to_overwrite_an_existing_artifact(tmp_path, workspace):
    """The one that turns a matrix uploading a single name into a red build —
    which is exactly what it does on GitHub, and the reason `name:` usually
    carries `${{ matrix.os }}`."""
    _write(workspace / "dist" / "app.js")
    inputs = {"name": "dist", "path": "dist/**"}

    assert run_builtin("actions/upload-artifact", _ctx(tmp_path, workspace, inputs)).ok
    second = run_builtin("actions/upload-artifact", _ctx(tmp_path, workspace, dict(inputs)))

    assert not second.ok
    assert "already exists" in second.message
    assert "overwrite" in second.message, "the message must name the way out"


def test_overwrite_true_replaces_it(tmp_path, workspace):
    _write(workspace / "dist" / "old.js")
    assert run_builtin(
        "actions/upload-artifact", _ctx(tmp_path, workspace, {"name": "d", "path": "dist/**"})
    ).ok

    (workspace / "dist" / "old.js").unlink()
    _write(workspace / "dist" / "new.js")
    second = run_builtin(
        "actions/upload-artifact",
        _ctx(tmp_path, workspace, {"name": "d", "path": "dist/**", "overwrite": True}),
    )

    assert second.ok, second.message
    stored = artifacts_mod.artifact_dir(tmp_path, "run-1", "d")
    names = sorted(p.name for p in stored.rglob("*.js"))
    assert names == ["new.js"], "overwrite REPLACES; it does not merge"


# --- download-artifact ------------------------------------------------------


def test_no_name_downloads_every_artifact_each_into_its_own_directory(tmp_path, workspace):
    """v4's headline change. The old default of `name="artifact"` downloaded
    one specific artifact that usually did not exist, so the step went green
    and the job failed later for an unrelated-looking reason."""
    _write(workspace / "out" / "index.js", "linux")
    run_builtin(
        "actions/upload-artifact", _ctx(tmp_path, workspace, {"name": "build-linux", "path": "out"})
    )
    _write(workspace / "out" / "index.js", "mac")
    run_builtin(
        "actions/upload-artifact", _ctx(tmp_path, workspace, {"name": "build-mac", "path": "out"})
    )

    into = tmp_path / "consumer"
    into.mkdir()
    result = run_builtin("actions/download-artifact", _ctx(tmp_path, into, {}))

    assert result.ok
    # `out/` keeps its shape inside each artifact; the artifact NAME is the
    # directory that keeps the two apart. Without that, both `index.js` land on
    # the same path and the second silently wins.
    assert (into / "build-linux" / "out" / "index.js").read_text(encoding="utf-8") == "linux"
    assert (into / "build-mac" / "out" / "index.js").read_text(encoding="utf-8") == "mac"


def test_pattern_selects_a_subset(tmp_path, workspace):
    for name in ("build-linux", "build-mac", "docs"):
        _write(workspace / "out" / f"{name}.txt", name)
        run_builtin(
            "actions/upload-artifact", _ctx(tmp_path, workspace, {"name": name, "path": "out"})
        )

    into = tmp_path / "consumer"
    into.mkdir()
    assert run_builtin("actions/download-artifact", _ctx(tmp_path, into, {"pattern": "build-*"})).ok

    assert sorted(p.name for p in into.iterdir()) == ["build-linux", "build-mac"]


def test_merge_multiple_flattens(tmp_path, workspace):
    for name in ("one", "two"):
        _write(workspace / "out" / f"{name}.txt", name)
        run_builtin(
            "actions/upload-artifact", _ctx(tmp_path, workspace, {"name": name, "path": "out"})
        )

    into = tmp_path / "consumer"
    into.mkdir()
    assert run_builtin(
        "actions/download-artifact", _ctx(tmp_path, into, {"merge-multiple": True})
    ).ok

    assert (into / "out" / "one.txt").exists()
    assert (into / "out" / "two.txt").exists()
    assert not (into / "one").exists(), "merge-multiple means no per-artifact directory"


def test_download_reports_where_it_put_things(tmp_path, workspace):
    result = run_builtin("actions/download-artifact", _ctx(tmp_path, workspace, {"name": "ghost"}))
    assert result.outputs["download-path"] == str(workspace)


# --- cache ------------------------------------------------------------------


def test_fail_on_cache_miss_fails(tmp_path, workspace, monkeypatch):
    """A release job that must not silently recompile what an earlier job was
    supposed to have cached."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")

    result = run_builtin(
        "actions/cache",
        _ctx(
            tmp_path,
            workspace,
            {"key": "deps-abc", "path": "node_modules", "fail-on-cache-miss": True},
        ),
    )

    assert not result.ok
    assert "fail-on-cache-miss" in result.message


def test_fail_on_cache_miss_is_satisfied_by_a_restore_key(tmp_path, workspace, monkeypatch):
    """A prefix hit reports `cache-hit: false` but it is NOT a miss — there was
    an entry. Failing here would break the commonest cache idiom there is."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "node_modules" / "left-pad" / "index.js")
    warm = _ctx(tmp_path, workspace, {"key": "deps-v1-aaa", "path": "node_modules"})
    run_builtin("actions/cache", warm)
    for action in warm.post:
        action()

    result = run_builtin(
        "actions/cache",
        _ctx(
            tmp_path,
            workspace,
            {
                "key": "deps-v1-bbb",
                "path": "node_modules",
                "restore-keys": "deps-v1-",
                "fail-on-cache-miss": True,
            },
        ),
    )

    assert result.ok, result.message
    assert result.outputs["cache-hit"] == "false"
    assert result.outputs["cache-matched-key"] == "deps-v1-aaa"


def test_lookup_only_answers_without_unpacking(tmp_path, workspace, monkeypatch):
    """The point of `lookup-only` is to decide whether to do the expensive
    thing. Restoring anyway is the difference between a warm workspace and a
    cold one, and it would also mask the build it was meant to skip."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "node_modules" / "left-pad" / "index.js")
    warm = _ctx(tmp_path, workspace, {"key": "deps-abc", "path": "node_modules"})
    run_builtin("actions/cache", warm)
    for action in warm.post:
        action()

    empty = tmp_path / "fresh"
    empty.mkdir()
    ctx = _ctx(tmp_path, empty, {"key": "deps-abc", "path": "node_modules", "lookup-only": True})
    result = run_builtin("actions/cache", ctx)

    assert result.outputs["cache-hit"] == "true"
    assert not (empty / "node_modules").exists(), "lookup-only must not extract"
    assert not ctx.post, "and it has nothing to save at job end"


def test_cache_reports_both_keys(tmp_path, workspace, monkeypatch):
    """`cache-hit: false` cannot distinguish "nothing at all" from "something
    close", and a workflow deciding whether to do a partial install needs to."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")

    result = run_builtin(
        "actions/cache", _ctx(tmp_path, workspace, {"key": "deps-abc", "path": "node_modules"})
    )

    assert result.outputs["cache-primary-key"] == "deps-abc"
    assert result.outputs["cache-matched-key"] == ""


# --- checkout ---------------------------------------------------------------


def test_fetch_depth_zero_gets_the_whole_history(tmp_path):
    """`git describe --tags` and anything counting commits break on a shallow
    tree, and the error never mentions the checkout that caused it."""
    import subprocess

    def git(cwd: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "a@b.c")
    git(repo, "config", "user.name", "t")
    for n in range(3):
        (repo / "f.txt").write_text(f"{n}\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", f"c{n}")

    ws = tmp_path / "ws"
    ws.mkdir()
    result = run_builtin(
        "actions/checkout",
        BuiltinContext(
            root=repo,
            run_id="run-1",
            workspace=ws,
            isolated=True,
            inputs={"fetch-depth": 0},
            emit=lambda _: None,
        ),
    )
    assert result.ok, result.message

    log = subprocess.run(
        ["git", "-C", str(ws), "log", "--oneline"], capture_output=True, text=True, check=True
    )
    assert len(log.stdout.strip().splitlines()) == 3, "fetch-depth: 0 means FULL history"
