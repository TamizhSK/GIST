"""A18/A19 — init templates and the bundled checkout action.

Acceptance: a generated flow parses clean (loader -> aliases -> builder, plus
the layer 1/2 checks), and the checkout action resolves through A17's resolver.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from yeet.actions.resolver import resolve
from yeet.cli.cmd_init import init
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.project import Ecosystem
from yeet.parser.aliases import normalize
from yeet.parser.builder import build_workflow
from yeet.parser.loader import load_with_positions
from yeet.templates import workflows
from yeet.validation.layer1_yaml import check as check_layer1
from yeet.validation.layer2_schema import check as check_layer2


def load_and_build(path: Path):
    bag = DiagnosticBag()
    data = load_with_positions(path, bag)
    assert data is not None, [d.message for d in bag.items]
    data, used = normalize(data)
    wf = build_workflow(data, path, bag)
    assert wf is not None
    wf.used_dialect = used
    assert not bag.items, [d.message for d in bag.items]
    return wf


def node_ecosystem() -> list[Ecosystem]:
    return [
        Ecosystem(
            name="node",
            marker=Path("package.json"),
            suggested_image="node:20",
            default_commands=["npm ci", "npm test"],
        )
    ]


def test_default_flow_renders_valid_yaml(tmp_path):
    flow = tmp_path / "main.yml"
    flow.write_text(workflows.default_flow("demo"), encoding="utf-8")
    wf = load_and_build(flow)

    assert wf is not None
    assert "build" in wf.jobs
    assert wf.jobs["build"].runs_on == "ubuntu-latest"
    assert len(wf.jobs["build"].steps) == 3


def test_auto_flow_has_ecosystem_job(tmp_path):
    flow = tmp_path / "main.yml"
    text = workflows.auto_flow("node-app", node_ecosystem(), dockerfile=False)
    flow.write_text(text, encoding="utf-8")
    wf = load_and_build(flow)

    assert wf is not None
    job = wf.jobs["node"]
    assert job.runs_on == "node:20"
    assert [s.run for s in job.steps if s.run] == ["npm ci", "npm test"]
    assert job.steps[0].uses == "./.yeet/actions/checkout"


def test_auto_flow_with_dockerfile(tmp_path):
    flow = tmp_path / "main.yml"
    flow.write_text(workflows.auto_flow("api", node_ecosystem(), dockerfile=True), encoding="utf-8")
    wf = load_and_build(flow)

    assert wf is not None
    container = wf.jobs["container"]
    assert container.runs_on is None
    assert any("docker build -t api ." in (s.run or "") for s in container.steps)


def test_generated_flow_passes_layer1_and_layer2(tmp_path):
    flow = tmp_path / "main.yml"
    flow.write_text(workflows.auto_flow("py-app", [
        Ecosystem(name="python", marker=tmp_path / "pyproject.toml",
                  suggested_image="python:3.12",
                  default_commands=["pip install -e .", "pytest"]),
    ], dockerfile=False), encoding="utf-8")

    bag1, data = check_layer1(flow)
    assert not bag1.items, [d.message for d in bag1.items]
    data, _used = normalize(data)
    bag2 = check_layer2(data, flow)
    assert not bag2.items, [d.message for d in bag2.items]


def test_flow_uses_dialect_keywords(tmp_path):
    flow = tmp_path / "main.yml"
    text = workflows.auto_flow("demo", node_ecosystem(), dockerfile=False)
    flow.write_text(text, encoding="utf-8")
    rendered = flow.read_text(encoding="utf-8")
    for token in ("vibe:", "the_grind:", "cooked_on:", "yoink:", "when:"):
        assert token in rendered
    wf = load_and_build(flow)
    assert wf.used_dialect is True


def test_checkout_action_renders_and_resolves(tmp_path):
    action_dir = tmp_path / "checkout"
    action_dir.mkdir()
    (action_dir / "action.yml").write_text(workflows.render_checkout_action(), encoding="utf-8")

    bag = DiagnosticBag()
    action = resolve("./checkout", tmp_path, bag)
    assert action is not None
    assert action.kind == "composite"
    assert not bag.items
    assert action.inputs["path"].default == "."
    assert action.steps[0].shell == "bash"


def test_bundled_checkout_action_resolves(tmp_path):
    repo_root = Path(__file__).parents[2]
    bundled = repo_root / ".yeet" / "actions" / "checkout"
    assert (bundled / "action.yml").is_file()

    bag = DiagnosticBag()
    action = resolve(str(bundled), repo_root, bag)
    assert action is not None
    assert action.kind == "composite"
    assert not bag.items


def test_init_scaffolds_flow_and_action(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # init default path is cwd
    init(Path(), auto=False)

    flow = tmp_path / ".yeet" / "flows" / "main.yml"
    action = tmp_path / ".yeet" / "actions" / "checkout" / "action.yml"
    gitignore = tmp_path / ".gitignore"
    assert flow.is_file()
    assert action.is_file()
    assert ".yeet/tmp/" in gitignore.read_text(encoding="utf-8")
    assert load_and_build(flow) is not None


def test_init_auto_uses_fingerprint(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    init(Path(), auto=True)

    flow = tmp_path / ".yeet" / "flows" / "main.yml"
    wf = load_and_build(flow)
    assert wf is not None
    assert wf.jobs["node"].runs_on == "node:20"


def test_init_refuses_to_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init(Path(), auto=False)
    with pytest.raises(typer.Exit) as exc:
        init(Path(), auto=False)
    assert exc.value.exit_code == 2


def test_gitignore_entries_are_not_duplicated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init(Path(), auto=False)
    init_ignores = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert init_ignores.count(".yeet/tmp/") == 1
