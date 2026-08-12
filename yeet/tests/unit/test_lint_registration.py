"""Layer 4 must actually fire in the product, not just in its own unit tests.

The bug this guards: rules self-register at import time, `layer4_lint/__init__`
was empty, and the pipeline imported `layer4_lint.base` — which loads the
registry and none of the rules. `RULES` was `[]` at runtime for three sessions.
`yeet check` on a workflow using `actions/checkout@main` printed nothing and
exited 0, while `test_lint.py` passed because it imports the rule classes
directly and thereby registers them itself.

Every test here therefore goes through a public entry point and asserts on
behaviour a user would see.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from yeet.validation.layer4_lint import RULE_MODULES, RULES
from yeet.validation.pipeline import validate_file

PACKAGE_DIR = Path(__file__).parents[2] / "src" / "yeet" / "validation" / "layer4_lint"


def test_importing_the_package_registers_rules() -> None:
    assert RULES, "no lint rules registered — layer 4 is dead in production"


def test_every_rule_module_on_disk_is_imported() -> None:
    """Adding `layer4_lint/foo.py` without listing it registers nothing.

    That is a silent failure — the rule is written, reviewed, tested in
    isolation, and never runs — so it is worth a test that reads the directory.
    """
    on_disk = {
        path.stem for path in PACKAGE_DIR.glob("*.py") if path.stem not in {"__init__", "base"}
    }
    assert on_disk == set(RULE_MODULES), (
        "rule modules on disk do not match layer4_lint/__init__.py's RULE_MODULES; "
        "add the module to both the `from . import` line and RULE_MODULES"
    )


def test_a_fresh_interpreter_importing_only_the_pipeline_still_lints() -> None:
    """The real configuration: no test has pre-imported anything.

    Run in a subprocess so this file's own imports cannot mask the gap.
    """
    code = (
        "from yeet.validation.pipeline import validate_file;"
        "from yeet.validation.layer4_lint import RULES;"
        "print(len(RULES))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert int(result.stdout.strip()) > 0


def test_lints_reach_the_user_through_validate_file(tmp_path: Path) -> None:
    """End to end: a moving action ref must produce W402 from `validate_file`."""
    flow = tmp_path / "main.yml"
    flow.write_text(
        "name: ci\n"
        "on: {push: {}}\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: checkout\n"
        "        uses: actions/checkout@main\n",
        encoding="utf-8",
    )

    bag, workflow = validate_file(flow, upto=4)
    assert workflow is not None
    assert "YEET-W402" in {d.code for d in bag.items}


def test_lint_yml_can_silence_a_rule(tmp_path: Path) -> None:
    """The override path, also only reachable once rules are registered."""
    (tmp_path / ".yeet").mkdir()
    (tmp_path / ".yeet" / "lint.yml").write_text("YEET-W402: off\n", encoding="utf-8")

    flow = tmp_path / "main.yml"
    flow.write_text(
        "name: ci\n"
        "on: {push: {}}\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: checkout\n"
        "        uses: actions/checkout@main\n",
        encoding="utf-8",
    )

    bag, _ = validate_file(flow, upto=4)
    assert "YEET-W402" not in {d.code for d in bag.items}
