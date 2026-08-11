"""Runs layers 0-4 in order. Stops BETWEEN layers on error, not within one.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Workflow


def validate_file(
    path: Path, *, strict: bool = False, upto: int = 4
) -> tuple[DiagnosticBag, Workflow | None]:
    """layer0 -> layer1 -> layer2 -> layer3 -> layer4. Return everything found.

    Returns the built Workflow alongside the bag so `cmd_run` can validate and
    then plan without parsing the file a second time. It is None whenever a
    layer below 3 produced an error and parsing stopped.

    Stop BETWEEN layers, never within one: there is no point schema-checking a
    file that is not valid YAML, but a user who fixes one broken `needs:` per
    run will hate this tool.

    `upto` is what makes every command a prefix of the same pipeline:
      scan -> upto=2   check -> upto=4   run -> upto=3 (+ layer 4, non-blocking)
    """
    bag = DiagnosticBag()
    workflow: Workflow | None = None

    # --- Layer 0: File & encoding checks (Dev D) ---
    from yeet.validation import layer0_file

    try:
        bag0 = layer0_file.check(path)
        bag.extend(bag0)
        if bag.has_errors() or upto < 1:
            return bag, workflow
    except NotImplementedError:
        pass

    # --- Layer 1: YAML parsing & aliases (Dev A) ---
    from yeet.validation import layer1_yaml

    data: object | None = None
    try:
        bag1, data = layer1_yaml.check(path)
        bag.extend(bag1)
        if bag.has_errors() or data is None or upto < 2:
            return bag, workflow
    except NotImplementedError:
        # Layer 1 not implemented yet by Dev A
        return bag, workflow

    # --- Layer 2: Schema validation (Dev A) ---
    from yeet.validation import layer2_schema

    try:
        bag2 = layer2_schema.check(data, path)
        bag.extend(bag2)
        if bag.has_errors() or upto < 3:
            return bag, workflow
    except NotImplementedError:
        pass

    # --- Parser / Builder: dict -> Workflow IR (Dev A) ---
    try:
        from yeet.parser.builder import build_workflow

        workflow = build_workflow(data, path, bag)
    except (NotImplementedError, Exception):
        workflow = None

    if workflow is None or upto < 3:
        return bag, workflow

    # --- Layer 3: Semantic validation (Dev B) ---
    from yeet.validation import layer3_semantic

    try:
        bag3 = layer3_semantic.check(workflow)
        bag.extend(bag3)
        if bag.has_errors() or upto < 4:
            return bag, workflow
    except NotImplementedError:
        pass

    # --- Layer 4: Lint / Code standards (Dev D) ---
    try:
        from yeet.core.config import load_lint_config
        from yeet.validation.layer4_lint.base import run_lints

        cfg = load_lint_config(path.parent)
        bag4 = run_lints(workflow, path, cfg)
        bag.extend(bag4)
    except (NotImplementedError, ImportError):
        pass

    return bag, workflow
