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

import io
import tarfile
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


# --- the hand-rolled `data` filter -------------------------------------------
#
# Reached only on 3.9.16- / 3.10.11- / 3.11.3-, which is not this interpreter
# and is exactly why it needs its own tests: `setup-python` ships 3.10.11 as the
# newest 3.10 for macOS, so the branch is live on a platform we support and dead
# on the one we develop on. `no_filter_kwarg` makes it the branch taken here.


@pytest.fixture
def no_filter_kwarg(monkeypatch):
    """`TarFile.extractall` as it was before the `filter=` backport."""
    real = tarfile.TarFile.extractall

    def old(self, path=".", members=None, *, numeric_owner=False):
        return real(self, path, members, numeric_owner=numeric_owner)

    monkeypatch.setattr(tarfile.TarFile, "extractall", old)


def _tar_with(tar_path: Path, name: str, payload: bytes = b"pwned") -> None:
    """`addfile`, not `add` — `add` normalises a leading `/` away, so the
    absolute-path case would test something the archive no longer contains."""
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    with tarfile.open(tar_path, "w") as tar:
        tar.addfile(info, io.BytesIO(payload))


@pytest.mark.parametrize(
    "arcname", ["../escaped.txt", "/etc/escaped.txt", "a/../../escaped.txt", "C:\\escaped.txt"]
)
def test_the_fallback_refuses_every_way_out_of_the_destination(tmp_path, no_filter_kwarg, arcname):
    tar_path = tmp_path / "evil.tar"
    _tar_with(tar_path, arcname)
    dest = tmp_path / "dest"

    with pytest.raises(tarfile.TarError):
        cache_mod._extract(tar_path, dest)

    assert not (tmp_path / "escaped.txt").exists()


def test_the_fallback_refuses_a_symlink_pointing_out(tmp_path, no_filter_kwarg):
    """The member itself is in bounds; its TARGET is not. Checking only the
    name lets an archive drop a link to `/etc/passwd` into the workspace."""
    tar_path = tmp_path / "link.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo("inside/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../../../etc/passwd"
        tar.addfile(info)

    with pytest.raises(tarfile.TarError):
        cache_mod._extract(tar_path, tmp_path / "dest")


def test_the_fallback_rejects_before_it_writes_anything(tmp_path, no_filter_kwarg):
    """A safe member ahead of an unsafe one must not survive the refusal —
    a half-restored cache is a cache the next step will trust."""
    tar_path = tmp_path / "mixed.tar"
    good = _write(tmp_path / "good.txt")
    with tarfile.open(tar_path, "w") as tar:
        tar.add(good, arcname="good.txt")
        tar.add(good, arcname="../escaped.txt")
    dest = tmp_path / "dest"

    with pytest.raises(tarfile.TarError):
        cache_mod._extract(tar_path, dest)

    assert not (dest / "good.txt").exists()


def test_the_fallback_still_restores_an_ordinary_cache(tmp_path, no_filter_kwarg, workspace):
    """The refusals above are worthless if the branch cannot do its job."""
    _write(workspace / "node_modules" / "dep" / "index.js", "module.exports = 1")
    tar_path = tmp_path / "good.tar"
    with tarfile.open(tar_path, "w") as tar:
        tar.add(workspace / "node_modules", arcname="node_modules")
    dest = tmp_path / "dest"

    cache_mod._extract(tar_path, dest)

    assert (dest / "node_modules" / "dep" / "index.js").read_text() == "module.exports = 1"


# --- checkout ---------------------------------------------------------------


def test_checkout_is_a_no_op_that_says_so(tmp_path, workspace):
    """It is the first step of nearly every real workflow. A run whose opening
    line reads `skipped (not the vibe)` looks like something went wrong before
    anything started — and nothing did: the workspace IS the checkout."""
    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path, run_id="run-1", workspace=workspace, inputs={}, emit=lines.append
    )

    result = run_builtin("actions/checkout", ctx)

    assert result.ok
    assert any("already this repository" in line for line in lines), lines


def test_checkout_refuses_a_ref_without_a_path(tmp_path, workspace):
    """The one thing this must never do is fetch over the workspace.

    The user pointed yeet at a directory they are working in. Replacing its
    contents with a different ref would discard uncommitted work to satisfy a
    line in a YAML file, and no amount of logging makes that acceptable —
    `path:` is how `actions/checkout` already spells "somewhere else", so the
    refusal names it.
    """
    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs={"ref": "v1.2.3"},
        emit=lines.append,
    )

    result = run_builtin("actions/checkout", ctx)

    assert not result.ok
    assert "path:" in result.message, result.message
    assert "v1.2.3" in result.message


def test_checkout_fetches_a_ref_into_a_path(tmp_path, workspace):
    """A workflow checking out a second repo alongside the first is ordinary,
    and this is the case that used to be silently ignored."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=workspace, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "a@b.c")
    git("config", "user.name", "t")
    (workspace / "file.txt").write_text("v1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "one")
    git("tag", "v1")
    (workspace / "file.txt").write_text("v2\n", encoding="utf-8")
    git("commit", "-qam", "two")

    lines: list[str] = []
    ctx = BuiltinContext(
        root=tmp_path,
        run_id="run-1",
        workspace=workspace,
        inputs={"ref": "v1", "path": "old"},
        emit=lines.append,
    )

    result = run_builtin("actions/checkout", ctx)

    assert result.ok, result.message
    assert (workspace / "old" / "file.txt").read_text(encoding="utf-8").strip() == "v1"
    assert (workspace / "file.txt").read_text(encoding="utf-8").strip() == "v2", (
        "the working tree must be untouched"
    )
