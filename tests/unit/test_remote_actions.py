"""`uses: owner/repo@ref` — the fetch policy, and the wiring that uses it.

`resolve_remote` was written in session A20, unit-tested, and then never called
by anything, so every third-party composite action on earth was reported as
"could not be resolved to a local action". Two things had to be true before
calling it was honest:

* it could not fetch the ref W402 tells you to use — `git clone --branch <sha>`
  is not a thing git does, so the PINNED spelling failed 100% of the time;
* a `uses:` line that reaches the network mid-run needed a stated policy.

Both are pinned here. The policy: fetch on a miss and say so, cache by ref,
forever for a SHA or an exact tag and for a day for a moving one, and
`--offline` to refuse the network and report the miss against the workflow line.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from yeet.actions import resolver
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Step
from yeet.core.refs import is_moving, is_sha
from yeet.executor import uses as uses_mod

COMPOSITE = """
name: fetched
runs:
  using: composite
  steps:
    - run: echo from-the-cache
      shell: bash
"""

NODE_ACTION = """
name: fetched
runs:
  using: node20
  main: dist/index.js
"""


def _fake_fetch(body: str = COMPOSITE, log: list | None = None):
    """Stands in for the network. Records what it was asked for."""

    def _clone(url: str, ref: str, dest: Path) -> bool:
        if log is not None:
            log.append((url, ref))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "action.yml").write_text(textwrap.dedent(body), encoding="utf-8")
        return True

    return _clone


def _step(uses: str) -> Step:
    from yeet.core.diagnostics import Position

    return Step(pos=Position.unknown(), uses=uses)


# --- which refs may be reused ------------------------------------------------


@pytest.mark.parametrize("ref", ["main", "master", "latest", "v4", "V2", "HEAD"])
def test_moving_refs_are_recognised(ref):
    assert is_moving(ref)


@pytest.mark.parametrize("ref", ["v4.1.0", "1.2.3", "release-2024", "a" * 40])
def test_pinned_refs_are_not(ref):
    assert not is_moving(ref)


def test_a_sha_is_the_one_immutable_ref():
    assert is_sha("0" * 40)
    assert not is_sha("v4")
    assert not is_sha("0" * 39)


def test_the_lint_and_the_cache_agree(tmp_path):
    """One definition, in `core/refs.py`. Two copies would have been free to
    drift — the lint warning about `@v5` while the cache treated it as
    immutable — with nothing able to fail when they did."""
    from conftest import make_job, make_workflow

    from yeet.validation.layer4_lint.pinning import PinningRule

    wf = make_workflow({"b": make_job("b", [_step("actions/checkout@v5")])})
    codes = [d.code for d in PinningRule().check(wf, tmp_path / "w.yml")]

    assert "YEET-W402" in codes
    assert is_moving("v5"), "the cache must call moving exactly what the lint does"


# --- the cache --------------------------------------------------------------


def test_a_pinned_ref_is_never_fetched_twice(tmp_path):
    log: list = []
    cache = tmp_path / "cache"
    sha = "a" * 40

    for _ in range(2):
        resolver.resolve_remote(
            f"actions/checkout@{sha}",
            DiagnosticBag(),
            cache_root=cache,
            git_clone=_fake_fetch(log=log),
        )

    assert len(log) == 1, "a SHA cannot have changed; re-fetching it is pure waste"


def test_a_moving_ref_is_refetched_once_it_is_stale(tmp_path, monkeypatch):
    """`@v4` is re-pointed at every minor release. Holding the first copy
    forever would silently pin the workflow to whatever landed first."""
    log: list = []
    cache = tmp_path / "cache"

    resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch(log=log)
    )
    assert len(log) == 1

    entry = cache / "actions" / "checkout" / resolver._ref_slug("v4")
    os.utime(entry, (0, 0))  # last fetched in 1970

    resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch(log=log)
    )
    assert len(log) == 2


def test_the_ttl_is_configurable_and_can_be_switched_off(tmp_path, monkeypatch):
    log: list = []
    cache = tmp_path / "cache"
    monkeypatch.setenv("YEET_ACTION_TTL", "0")

    resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch(log=log)
    )
    os.utime(cache / "actions" / "checkout" / resolver._ref_slug("v4"), (0, 0))
    resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch(log=log)
    )

    assert len(log) == 1, "TTL 0 means never re-fetch"


def test_junk_in_the_ttl_is_the_default_not_a_crash(tmp_path, monkeypatch):
    """A typo'd environment variable must not stop a run. Guessing wrong costs
    one fetch; raising costs the whole workflow."""
    monkeypatch.setenv("YEET_ACTION_TTL", "soon")
    assert resolver._ttl_s() == resolver.DEFAULT_TTL_S


def test_a_failed_fetch_leaves_no_half_written_entry(tmp_path):
    """Otherwise every later run resolves against the wreckage, and the error
    is about a malformed action.yml rather than about the fetch that failed."""
    cache = tmp_path / "cache"
    bag = DiagnosticBag()

    def _broken(url: str, ref: str, dest: Path) -> bool:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "partial").write_text("half a repo", encoding="utf-8")
        return False

    action = resolver.resolve_remote(
        "actions/checkout@v4", bag, cache_root=cache, git_clone=_broken
    )

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]
    assert not (cache / "actions" / "checkout" / resolver._ref_slug("v4")).exists()


def test_prune_empties_the_cache(tmp_path):
    cache = tmp_path / "cache"
    for ref in ("v4", "v5"):
        resolver.resolve_remote(
            f"actions/checkout@{ref}", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch()
        )

    assert resolver.prune_actions(cache) == 2
    assert not cache.exists()
    assert resolver.prune_actions(cache) == 0, "and it is safe to run twice"


# --- offline ----------------------------------------------------------------


def test_offline_serves_a_hit(tmp_path):
    cache = tmp_path / "cache"
    resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, git_clone=_fake_fetch()
    )

    action = resolver.resolve_remote(
        "actions/checkout@v4", DiagnosticBag(), cache_root=cache, offline=True
    )

    assert action is not None, "offline must not break what is already cached"


def test_offline_refuses_a_miss(tmp_path):
    with pytest.raises(resolver.Offline):
        resolver.resolve_remote(
            "actions/checkout@v4", DiagnosticBag(), cache_root=tmp_path / "cache", offline=True
        )


def test_offline_reaches_the_user_as_a_reason_not_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "REMOTE_CACHE_ROOT", tmp_path / "cache")

    plan = uses_mod.plan_uses(_step("some/action@v1"), tmp_path, DiagnosticBag(), offline=True)

    assert plan.kind == uses_mod.UNSUPPORTED
    assert plan.blocking, (
        "an action we could not GET must fail, not skip. Skipped is green, and "
        "green has to mean the workflow would pass on GitHub"
    )
    assert "--offline" in plan.reason
    assert "action cache" in plan.reason or "cache" in plan.reason


# --- the wiring -------------------------------------------------------------


def test_a_remote_composite_action_is_inlined(tmp_path, monkeypatch):
    """The whole point. Before this it was skipped as "could not be resolved"
    while a tested module sat one call away."""
    monkeypatch.setattr(resolver, "REMOTE_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(resolver, "_git_clone", _fake_fetch())

    plan = uses_mod.plan_uses(_step("some/action@v1"), tmp_path, DiagnosticBag())

    assert plan.kind == uses_mod.INLINE
    assert [s.run for s in plan.steps] == ["echo from-the-cache"]


def test_a_remote_node_action_says_which_kind_it_is(tmp_path, monkeypatch):
    """We fetched it and read its action.yml, so "could not be resolved" is no
    longer true — and a user chasing C15/C16 can see which one they need."""
    monkeypatch.setattr(resolver, "REMOTE_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(resolver, "_git_clone", _fake_fetch(NODE_ACTION))

    plan = uses_mod.plan_uses(_step("some/action@v1"), tmp_path, DiagnosticBag())

    assert plan.kind == uses_mod.UNSUPPORTED
    assert "node action" in plan.reason
    assert "C16" in plan.reason
    assert not plan.blocking, (
        "a kind we chose not to run yet stays skipped-green; only an action we "
        "could not obtain is a failure"
    )


def test_the_fetch_is_announced(tmp_path, monkeypatch):
    """A run that pauses for ten seconds must say what it is waiting for, and
    reaching the network from a YAML line should never be silent."""
    monkeypatch.setattr(resolver, "REMOTE_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(resolver, "_git_clone", _fake_fetch())
    said: list[str] = []

    uses_mod.plan_uses(_step("some/action@v1"), tmp_path, DiagnosticBag(), on_fetch=said.append)

    assert said == ["some/action@v1"]


def test_builtins_still_win_over_the_remote_path(tmp_path, monkeypatch):
    """`actions/checkout@v4` matches `owner/repo@ref` too. It must stay a
    built-in — fetching and inlining the real one would run its JavaScript
    against an artifact service that does not exist here."""

    def _never(url, ref, dest):  # pragma: no cover - the assertion is that it is not called
        raise AssertionError("a built-in must not reach the network")

    monkeypatch.setattr(resolver, "_git_clone", _never)

    plan = uses_mod.plan_uses(_step("actions/checkout@v4"), tmp_path, DiagnosticBag())

    assert plan.kind == uses_mod.BUILTIN


def test_a_composites_inputs_reach_the_expression_engine(tmp_path):
    """`${{ inputs.path }}` inside an action resolved to "" for as long as
    composite actions have run here.

    `INPUT_PATH` in the env always worked, so the shell form was fine and the
    expression form was a silent empty string — two spellings of one value,
    one of them a lie. Real actions use both, often in the same file.
    """
    action_dir = tmp_path / "act"
    action_dir.mkdir()
    resolved = resolver.ResolvedAction(
        kind="composite",
        action_dir=action_dir,
        inputs={
            "path": resolver.InputSpec(name="path", default="."),
            "name": resolver.InputSpec(name="name", default="artifact"),
        },
        steps=[Step(pos=_step("x").pos, run="echo ${{ inputs.path }}")],
    )

    out = resolver.composite_steps(resolved, {}, {"path": "src"})

    assert out[0].action_inputs == {"path": "src", "name": "artifact"}, (
        "`with:` over the action's own defaults, keyed by the declared name"
    )


def test_a_workflow_step_has_no_action_inputs(tmp_path):
    """The distinction that makes the field safe: a `workflow_call` input is a
    different thing with the same spelling, and must not be overwritten."""
    assert _step("actions/checkout@v4").action_inputs is None


def test_container_paths_in_a_builtins_inputs_come_back_to_the_host(tmp_path):
    """A built-in runs on the HOST; a real action computes `/workspace/...`.

    `upload-pages-artifact` tars into `${{ runner.temp }}` and hands that path
    to `upload-artifact`, so the built-in was told to look somewhere that
    exists nowhere on this machine — and reported "no files matched" for a file
    that had just been written.
    """
    from conftest import make_job

    from yeet.executor.paths import CONTAINER_WORKSPACE
    from yeet.executor.steps import StepLoopConfig, _to_host_path
    from yeet.executor.workspace import create

    ws = tmp_path / "ws"
    ws.mkdir()
    config = StepLoopConfig(
        job=make_job(),
        job_key="build",
        layout=create(tmp_path, "run-1").job("build"),
        root=tmp_path,
        workspace=ws,
        base_env={},
        masker=__import__("yeet.core.masking", fromlist=["Masker"]).Masker(),
        to_step_path=str,
    )

    assert _to_host_path(f"{CONTAINER_WORKSPACE}/dist/app.js", config) == str(ws / "dist/app.js")
    assert _to_host_path(CONTAINER_WORKSPACE, config) == str(ws)
    # A relative path and a genuine host path are left exactly as they are.
    assert _to_host_path("dist/**", config) == "dist/**"
    assert _to_host_path("/etc/hosts", config) == "/etc/hosts"
    # `path:` is multi-line in every real workflow that uses it.
    assert _to_host_path(f"dist\n{CONTAINER_WORKSPACE}/out\n", config) == f"dist\n{ws / 'out'}"


def test_a_composites_own_relative_uses_is_rebased_onto_the_action(tmp_path):
    """`uses: ./x` inside a cloned action means "relative to the ACTION".

    Once inlined the steps are indistinguishable from the job's own, and the
    job resolves `./x` against the workspace — which for a cached action is a
    different repository entirely.
    """
    action_dir = tmp_path / "cache" / "some" / "action" / "v1"
    action_dir.mkdir(parents=True)
    resolved = resolver.ResolvedAction(
        kind="composite",
        action_dir=action_dir,
        steps=[_step("./inner"), _step("actions/other@v2"), _step("docker://alpine:3.20")],
    )

    out = resolver.composite_steps(resolved, {})

    assert out[0].uses == str(action_dir / "inner")
    assert out[1].uses == "actions/other@v2", "a remote ref means the same thing anywhere"
    assert out[2].uses == "docker://alpine:3.20"
