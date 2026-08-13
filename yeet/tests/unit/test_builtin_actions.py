"""upload-artifact / download-artifact / cache, and the storage behind them.

`storage/artifacts.py` and `storage/cache.py` were written in session 2 and had
no call site in the product until now — the sixth instance in this project of a
finished module nothing reaches. Their unit tests passed throughout, which is
exactly why the gap survived: a test that calls the module directly cannot
notice that nothing else does.

Two of the behaviours pinned here were not merely unreachable, they were wrong:
restore-keys did no prefix matching at all, and members were tarred by bare
name so two `dist/` directories collided.
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
    path.write_text(text, encoding="utf-8")
    return path


# --- artifacts --------------------------------------------------------------


def test_upload_then_download_round_trips_a_directory(tmp_path, workspace):
    _write(workspace / "dist" / "app.js", "console.log(1)")
    _write(workspace / "dist" / "nested" / "chunk.js", "chunk")

    ctx = _ctx(tmp_path, workspace, {"name": "dist", "path": "dist/**"})
    up = run_builtin("actions/upload-artifact", ctx)
    assert up.ok

    other = tmp_path / "consumer"
    other.mkdir()
    down = run_builtin("actions/download-artifact", _ctx(tmp_path, other, {"name": "dist"}))
    assert down.ok

    assert (other / "dist" / "app.js").read_text(encoding="utf-8") == "console.log(1)"
    assert (other / "dist" / "nested" / "chunk.js").exists(), "layout must survive the trip"


def test_uploading_a_pattern_that_matches_nothing_warns_rather_than_fails(tmp_path, workspace):
    """GitHub warns here. Failing the job would break workflows that upload
    output which is legitimately optional."""
    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs={"name": "dist", "path": "dist/**"},
        emit=lines.append,
    )

    result = run_builtin("actions/upload-artifact", ctx)

    assert result.ok
    assert any("no files matched" in line for line in lines)


def test_a_bare_directory_path_uploads_its_contents(tmp_path, workspace):
    _write(workspace / "logs" / "a.log")
    _write(workspace / "logs" / "b.log")

    ctx = _ctx(tmp_path, workspace, {"name": "logs", "path": "logs"})
    run_builtin("actions/upload-artifact", ctx)

    stored = artifacts_mod.artifact_dir(tmp_path, "run-1", "logs")
    assert sorted(p.name for p in stored.rglob("*.log")) == ["a.log", "b.log"]


def test_downloading_an_artifact_that_does_not_exist_is_not_a_failure(tmp_path, workspace):
    result = run_builtin("actions/download-artifact", _ctx(tmp_path, workspace, {"name": "ghost"}))
    assert result.ok


# --- cache ------------------------------------------------------------------


def test_cache_miss_then_hit(tmp_path, workspace, monkeypatch):
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "node_modules" / "left-pad" / "index.js", "module.exports=1")

    first = run_builtin(
        "actions/cache", _ctx(tmp_path, workspace, {"key": "deps-abc", "path": "node_modules"})
    )
    assert first.outputs["cache-hit"] == "false"

    ctx = _ctx(tmp_path, workspace, {"key": "deps-abc", "path": "node_modules"})
    ctx.post.clear()
    run_builtin("actions/cache", ctx)
    for action in ctx.post:
        action()

    # A fresh workspace, same key: the cache must repopulate it.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    second = run_builtin(
        "actions/cache", _ctx(tmp_path, fresh, {"key": "deps-abc", "path": "node_modules"})
    )

    assert second.outputs["cache-hit"] == "true"
    assert (fresh / "node_modules" / "left-pad" / "index.js").exists()


def test_restore_keys_match_by_PREFIX(tmp_path, workspace, monkeypatch):
    """The entire point of restore-keys, and it did not work.

    The first implementation hashed each restore key and looked for that exact
    hash on disk. Hashing destroys prefixes, so `deps-` could never match
    `deps-abc123` — a restore key only ever hit when it exactly equalled the
    key that saved the entry, which is the one case it is not for.
    """
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "node_modules" / "dep.js")
    cache_mod.save_cache("deps-lockfile-abc123", [workspace / "node_modules"], base=workspace)

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    result = run_builtin(
        "actions/cache",
        _ctx(
            tmp_path,
            fresh,
            {"key": "deps-lockfile-zzz999", "path": "node_modules", "restore-keys": "deps-"},
        ),
    )

    assert (fresh / "node_modules" / "dep.js").exists(), "restore-key prefix must hit"
    assert result.outputs["cache-hit"] == "false", "a prefix hit is not an exact hit"


def test_a_prefix_hit_still_saves_the_exact_key_at_job_end(tmp_path, workspace, monkeypatch):
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "deps" / "a")
    cache_mod.save_cache("deps-old", [workspace / "deps"], base=workspace)

    ctx = _ctx(tmp_path, workspace, {"key": "deps-new", "path": "deps", "restore-keys": "deps-"})
    run_builtin("actions/cache", ctx)

    assert ctx.post, "a non-exact hit must still save under the new key"
    for action in ctx.post:
        action()
    assert cache_mod.entry_path("deps-new").is_file()


def test_an_exact_hit_does_not_re_save(tmp_path, workspace, monkeypatch):
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "deps" / "a")
    cache_mod.save_cache("deps-1", [workspace / "deps"], base=workspace)

    ctx = _ctx(tmp_path, workspace, {"key": "deps-1", "path": "deps"})
    run_builtin("actions/cache", ctx)

    assert ctx.post == [], "re-tarring an unchanged directory is pure cost"


def test_cached_paths_keep_their_position_in_the_workspace(tmp_path, workspace, monkeypatch):
    """`arcname=p.name` flattened everything: `src/dist` and `web/dist` both
    became `dist`, and restoring either wrote over the workspace root."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "src" / "dist" / "a.js", "src")
    _write(workspace / "web" / "dist" / "b.js", "web")

    cache_mod.save_cache(
        "two", [workspace / "src" / "dist", workspace / "web" / "dist"], base=workspace
    )

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    hit = cache_mod.restore_cache("two", None, dest=fresh)

    assert hit is not None and hit.exact
    assert (fresh / "src" / "dist" / "a.js").read_text(encoding="utf-8") == "src"
    assert (fresh / "web" / "dist" / "b.js").read_text(encoding="utf-8") == "web"


def test_a_cache_needs_both_a_key_and_a_path(tmp_path, workspace, monkeypatch):
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    result = run_builtin("actions/cache", _ctx(tmp_path, workspace, {"key": "k"}))
    assert not result.ok


def test_keys_that_slug_the_same_do_not_share_an_entry(tmp_path, monkeypatch, workspace):
    """`feat/x` and `feat-x` both slug to `feat-x`; the sidecar holds the real
    key so a prefix match cannot restore the wrong cache."""
    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    _write(workspace / "d" / "a")

    cache_mod.save_cache("feat/x", [workspace / "d"], base=workspace)
    cache_mod.save_cache("feat-x", [workspace / "d"], base=workspace)

    assert cache_mod.entry_path("feat/x") != cache_mod.entry_path("feat-x")


def test_extraction_refuses_to_escape_the_destination(tmp_path, monkeypatch, workspace):
    """A cache tarball is attacker-controlled the moment a cache directory is
    shared. `filter="data"` is what keeps `../../` inside the workspace."""
    import tarfile

    monkeypatch.setattr(cache_mod, "cache_dir", lambda: tmp_path / "cachehome")
    store = tmp_path / "cachehome" / "cache"
    store.mkdir(parents=True)
    evil = _write(tmp_path / "evil.txt", "pwned")

    tar_path = cache_mod.entry_path("evil")
    with tarfile.open(tar_path, "w") as tar:
        tar.add(evil, arcname="../../escaped.txt")
    tar_path.with_suffix(".key").write_text("evil", encoding="utf-8")

    dest = tmp_path / "dest"
    with pytest.raises(tarfile.TarError):
        cache_mod.restore_cache("evil", None, dest=dest)

    assert not (tmp_path / "escaped.txt").exists()
