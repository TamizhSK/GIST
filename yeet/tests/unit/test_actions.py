"""A17 — actions resolver: local composite inlining, INPUT_* env, E313/E314/W319.

Resolver is pure: `uses:` in, IR out. No processes here.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from yeet.actions.composite import inline
from yeet.actions.resolver import apply_inputs, resolve, resolve_remote
from yeet.core.diagnostics import DiagnosticBag
from yeet.parser.aliases import normalize
from yeet.parser.builder import build_workflow
from yeet.parser.loader import load_with_positions


def _step_dict(s):
    return {
        "name": s.name,
        "id": s.id,
        "run": s.run,
        "uses": s.uses,
        "with": s.with_,
        "env": s.env,
        "if": s.if_,
        "shell": s.shell,
        "working_directory": s.working_directory,
        "continue_on_error": s.continue_on_error,
        "timeout_minutes": s.timeout_minutes,
    }


def write_action(root: Path, name: str, body: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "action.yml").write_text(textwrap.dedent(body), encoding="utf-8")
    return d


GIT_CLONE = """\
name: "git clone"
description: "clone a repo"
inputs:
  repo:
    description: "repo to clone"
    required: true
  depth:
    description: "shallow clone depth"
    default: "0"
runs:
  using: composite
  steps:
    - name: "clone it"
      run: "git clone --depth ${{ inputs.depth }} ${{ inputs.repo }}"
      shell: bash
"""


def test_local_composite_resolves_with_steps(tmp_path):
    write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()

    action = resolve("./checkout", tmp_path, bag)

    assert action is not None
    assert action.kind == "composite"
    assert not bag.items
    assert action.inputs["repo"].required is True
    assert action.inputs["depth"].default == "0"
    assert len(action.steps) == 1
    assert action.steps[0].run == "git clone --depth ${{ inputs.depth }} ${{ inputs.repo }}"
    assert action.steps[0].shell == "bash"


def test_apply_inputs_with_defaults_and_required(tmp_path):
    write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)

    env = apply_inputs(action, {"repo": "org/app"}, bag)
    assert env["INPUT_REPO"] == "org/app"
    assert env["INPUT_DEPTH"] == "0"
    assert not bag.items


def test_e314_required_input_missing(tmp_path):
    write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)

    env = apply_inputs(action, {}, bag, file=Path("wf.yml"), pos=None)
    assert bag.has_errors()
    assert [d.code for d in bag.items] == ["YEET-E314"]
    assert "repo" in bag.items[0].message
    assert "repo" not in env


def test_w319_undeclared_input_warns(tmp_path):
    write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)

    env = apply_inputs(action, {"repo": "org/app", "branch": "main"}, bag)
    assert not bag.has_errors()
    assert [d.code for d in bag.items] == ["YEET-W319"]
    assert env["INPUT_REPO"] == "org/app"
    assert "INPUT_BRANCH" not in env


def test_composite_inline_merges_input_env(tmp_path):
    write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)

    steps = inline(action, {"repo": "org/app"}, bag)
    assert len(steps) == 1
    assert steps[0].env["INPUT_REPO"] == "org/app"
    assert steps[0].env["INPUT_DEPTH"] == "0"


def test_composite_inline_step_env_wins_over_inputs(tmp_path):
    write_action(
        tmp_path,
        "tagger",
        """\
        name: "tagger"
        inputs:
          value:
            default: "tag"
        runs:
          using: composite
          steps:
            - run: "git tag ${{ inputs.value }}"
              env:
                INPUT_VALUE: "explicit-wins"
        """,
    )
    bag = DiagnosticBag()
    action = resolve("./tagger", tmp_path, bag)

    steps = inline(action, {}, bag)
    assert steps[0].env["INPUT_VALUE"] == "explicit-wins"


def test_e313_missing_directory(tmp_path):
    bag = DiagnosticBag()
    action = resolve("./nope", tmp_path, bag)

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_e313_missing_action_yml(tmp_path):
    (tmp_path / "empty").mkdir()
    bag = DiagnosticBag()
    action = resolve("./empty", tmp_path, bag)

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_e313_invalid_yaml(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "action.yml").write_text("runs:\n  using: [unclosed", encoding="utf-8")
    bag = DiagnosticBag()

    action = resolve("./broken", tmp_path, bag)

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_e313_no_runs_block(tmp_path):
    write_action(tmp_path, "noddy", "name: 'nothing here'\n")
    bag = DiagnosticBag()

    action = resolve("./noddy", tmp_path, bag)

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_e313_composite_without_steps(tmp_path):
    write_action(tmp_path, "empty", "runs:\n  using: composite\n")
    bag = DiagnosticBag()

    action = resolve("./empty", tmp_path, bag)

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_remote_refs_are_not_local(tmp_path):
    bag = DiagnosticBag()
    for uses in ("actions/checkout@v4", "docker://alpine:3.20", "ghcr.io/x/y@v1"):
        assert resolve(uses, tmp_path, bag) is None
        assert not bag.items


def test_absolute_path_action(tmp_path):
    write_action(tmp_path, "abs", GIT_CLONE)
    bag = DiagnosticBag()

    action = resolve(str(tmp_path / "abs"), tmp_path, bag)

    assert action is not None
    assert action.kind == "composite"


def test_node_action_metadata_resolves(tmp_path):
    write_action(
        tmp_path,
        "tool",
        """\
        name: "tool"
        inputs:
          flag:
            default: "off"
        runs:
          using: node20
          main: dist/index.js
        """,
    )
    bag = DiagnosticBag()

    action = resolve("./tool", tmp_path, bag)

    assert action is not None
    assert action.kind == "node"
    assert action.main == "dist/index.js"
    assert action.steps == []
    assert not bag.items


def test_docker_action_metadata_resolves(tmp_path):
    write_action(
        tmp_path,
        "dbuild",
        "runs:\n  using: docker\n  image: Dockerfile\n",
    )
    bag = DiagnosticBag()

    action = resolve("./dbuild", tmp_path, bag)

    assert action is not None
    assert action.kind == "docker"
    assert action.image == "Dockerfile"


def test_input_env_name_sanitises(tmp_path):
    from yeet.actions.resolver import input_env_name

    assert input_env_name("node-version") == "INPUT_NODE_VERSION"
    assert input_env_name("fetch depth 2") == "INPUT_FETCH_DEPTH_2"
    assert input_env_name("FOO") == "INPUT_FOO"


def test_resolved_action_keeps_action_dir(tmp_path):
    d = write_action(tmp_path, "checkout", GIT_CLONE)
    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)
    assert action.action_dir == d


def test_composite_expansion_golden():
    fixtures = Path(__file__).parents[1] / "fixtures" / "valid"
    yml = fixtures / "09-composite-action.yml"
    expanded = json.loads(
        (fixtures / "09-composite-action.expanded.json").read_text(encoding="utf-8")
    )

    bag = DiagnosticBag()
    data = load_with_positions(yml, bag)
    data, _ = normalize(data)
    wf = build_workflow(data, yml, bag)
    step = next(s for j in wf.jobs.values() for s in j.steps if s.uses)

    action = resolve(step.uses, fixtures, bag)
    assert action is not None
    steps = inline(action, step.with_, bag)

    assert [_step_dict(s) for s in steps] == expanded


# --- A20: remote owner/repo@ref --------------------------------------------


def _fake_clone(made: dict, cloned: list):
    def _clone(url: str, ref: str, dest) -> bool:
        cloned.append((url, ref, str(dest)))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "action.yml").write_text(textwrap.dedent(GIT_CLONE), encoding="utf-8")
        made[url] = dest
        return True

    return _clone


def test_remote_resolves_and_caches(tmp_path):
    bag = DiagnosticBag()
    cloned = []

    action = resolve_remote(
        "actions/checkout@v4",
        bag,
        cache_root=tmp_path / "cache",
        git_clone=_fake_clone({}, cloned),
    )

    assert action is not None
    assert action.kind == "composite"
    assert not bag.items
    assert cloned[0][0] == "https://github.com/actions/checkout.git"
    assert (tmp_path / "cache" / "actions" / "checkout" / "v4").is_dir()


def test_remote_cache_hit_skips_clone(tmp_path):
    bag = DiagnosticBag()
    cache = tmp_path / "cache"
    cloned = []
    resolve_remote("actions/checkout@v4", bag, cache_root=cache, git_clone=_fake_clone({}, cloned))
    assert cloned == [cloned[0]]
    n = len(cloned)

    resolve_remote("actions/checkout@v4", bag, cache_root=cache, git_clone=_fake_clone({}, cloned))
    assert len(cloned) == n


def test_remote_refs_are_distinct_by_ref(tmp_path):
    bag = DiagnosticBag()
    cache = tmp_path / "cache"
    cloned = []
    fake = _fake_clone({}, cloned)

    resolve_remote("actions/checkout@v4", bag, cache_root=cache, git_clone=fake)
    resolve_remote("actions/checkout@v5", bag, cache_root=cache, git_clone=fake)

    assert len(cloned) == 2
    assert (cache / "actions" / "checkout" / "v4").is_dir()
    assert (cache / "actions" / "checkout" / "v5").is_dir()


def test_remote_failed_clone_is_e313(tmp_path):
    bag = DiagnosticBag()

    def _boom(url, ref, dest) -> bool:
        return False

    action = resolve_remote(
        "actions/checkout@v4", bag, cache_root=tmp_path / "cache", git_clone=_boom
    )

    assert action is None
    assert [d.code for d in bag.items] == ["YEET-E313"]


def test_remote_ignores_non_ref_uses(tmp_path):
    bag = DiagnosticBag()
    assert resolve_remote("docker://alpine:3.20", bag) is None
    assert resolve_remote("setup-node", bag) is None
    assert not bag.items
