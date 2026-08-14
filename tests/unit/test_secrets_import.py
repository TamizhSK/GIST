"""`yeet secrets import`, and the secret/variable split it depends on.

The split is the load-bearing part. Locally there is ONE pool of values —
`.env` plus the encrypted store — and nothing in it says which entries are
secrets. Only the workflow knows, because only the workflow spells
`${{ secrets.X }}` or `${{ vars.Y }}`. Getting it wrong is not cosmetic: mask a
variable and every occurrence of its value turns into `***` in the log
(`vars.NODE_ENV=production` would redact the word "production"); fail to mask a
secret and it is in the log and in `.yeet/runs/` forever.
"""

from __future__ import annotations

from pathlib import Path

from conftest import make_job, make_step, make_workflow

from yeet.core.ir import Workflow
from yeet.validation.layer3_semantic import referenced_names


def _wf(**kwargs: object) -> Workflow:
    return make_workflow({"build": make_job("build", **kwargs)})  # type: ignore[arg-type]


def test_secret_and_variable_references_are_told_apart() -> None:
    wf = _wf(
        env={"REGION": "${{ vars.AWS_REGION }}"},
        steps=[make_step("deploy", env={"T": "${{ secrets.NPM_TOKEN }}"})],
    )

    assert referenced_names(wf, "secrets") == {"NPM_TOKEN"}
    assert referenced_names(wf, "vars") == {"AWS_REGION"}


def test_a_name_used_in_run_text_counts() -> None:
    wf = _wf(steps=[make_step("echo ${{ secrets.A }} ${{ vars.B }}")])

    assert referenced_names(wf, "secrets") == {"A"}
    assert referenced_names(wf, "vars") == {"B"}


def test_whitespace_around_the_dot_does_not_hide_a_reference() -> None:
    """`${{ secrets . TOKEN }}` is legal in the expression grammar, and a
    scanner that misses it would leave the value unmasked."""
    wf = _wf(steps=[make_step("echo ${{ secrets . TOKEN }}")])

    assert referenced_names(wf, "secrets") == {"TOKEN"}


def test_workflow_level_env_is_scanned() -> None:
    """`Workflow.env` was parsed and dropped on the floor once already."""
    wf = make_workflow({"build": make_job("build")})
    wf.env = {"T": "${{ secrets.TOP_LEVEL }}"}

    assert referenced_names(wf, "secrets") == {"TOP_LEVEL"}


def test_nothing_referenced_is_an_empty_set_not_an_error() -> None:
    assert referenced_names(_wf(steps=[make_step("echo hi")]), "secrets") == set()


# --- the CLI ----------------------------------------------------------------


def _project(tmp_path: Path, body: str) -> Path:
    flows = tmp_path / ".github" / "workflows"
    flows.mkdir(parents=True)
    (flows / "ci.yml").write_text(body, encoding="utf-8", newline="\n")
    return tmp_path


WORKFLOW = """\
name: needs keys
on: [push]
jobs:
  deploy:
    runs-on: local
    env:
      REGION: ${{ vars.AWS_REGION }}
    steps:
      - run: echo hi
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
"""


def _import(root: Path, monkeypatch, **env: str):
    from typer.testing import CliRunner

    from yeet.cli.app import app

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return CliRunner().invoke(app, ["secrets", "import", "--path", str(root)])


def test_import_writes_every_referenced_name_to_dotenv(tmp_path, monkeypatch):
    root = _project(tmp_path, WORKFLOW)
    monkeypatch.delenv("AWS_REGION", raising=False)

    result = _import(root, monkeypatch, NPM_TOKEN="from-the-shell")

    assert result.exit_code == 0, result.output
    written = (root / ".env").read_text(encoding="utf-8")
    assert "NPM_TOKEN=from-the-shell" in written, "an exported value is picked up"
    assert "AWS_REGION=" in written, "an unset one is left blank to fill in"


def test_import_does_not_overwrite_a_value_already_in_dotenv(tmp_path, monkeypatch):
    """Safe to re-run after someone adds a workflow — and it must not clobber a
    token pasted in by hand."""
    root = _project(tmp_path, WORKFLOW)
    (root / ".env").write_text("NPM_TOKEN=pasted-by-hand\n", encoding="utf-8")

    _import(root, monkeypatch, NPM_TOKEN="from-the-shell")

    written = (root / ".env").read_text(encoding="utf-8")
    assert "pasted-by-hand" in written
    assert "from-the-shell" not in written


def test_import_skips_github_token(tmp_path, monkeypatch):
    """GitHub injects it; asking the user for it would be asking for something
    that does not exist locally."""
    root = _project(
        tmp_path,
        WORKFLOW.replace("secrets.NPM_TOKEN", "secrets.GITHUB_TOKEN"),
    )
    monkeypatch.delenv("AWS_REGION", raising=False)

    _import(root, monkeypatch)

    assert "GITHUB_TOKEN" not in (root / ".env").read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from yeet.cli.app import app

    root = _project(tmp_path, WORKFLOW)
    result = CliRunner().invoke(app, ["secrets", "import", "--path", str(root), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not (root / ".env").exists()
