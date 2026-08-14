"""Runs layers 0-4 in order. Stops BETWEEN layers on error, not within one.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md

WHY THE DIALECT PASS LIVES HERE
-------------------------------
`aliases.normalize()` runs between layer 1 and layer 2, and this is the only
place it is called in the product. Layer 2's schema validates the CANONICAL
form only (see the `description` in workflow.schema.json), so a dialect file
that is never normalized fails its own schema with a pile of E201s — which is
exactly what happened before this call existed: `yeet check` rejected the
walking-skeleton workflow printed in plan.md §6.

It sits in the pipeline rather than inside layer 1 because the pipeline is the
only component that runs layer 1 and layer 2 back to back, and because
`normalize()` returns the `used_dialect` flag that has to reach the Workflow.
`upto=2` (what `yeet scan` uses) still gets normalized data — the pass is
before the layer-2 early return, not after it.
"""

from __future__ import annotations

import os
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.ir import Workflow


def validate_file(
    path: Path, *, strict: bool = False, upto: int = 4
) -> tuple[DiagnosticBag, Workflow | None]:
    """layer0 -> layer1 -> aliases -> layer2 -> builder -> layer3 -> layer4.

    Returns the built Workflow alongside the bag so `cmd_run` can validate and
    then plan without parsing the file a second time. It is None whenever a
    layer below 3 produced an error and parsing stopped.

    Stop BETWEEN layers, never within one: there is no point schema-checking a
    file that is not valid YAML, but a user who fixes one broken `needs:` per
    run will hate this tool.

    `upto` is what makes every command a prefix of the same pipeline:
      scan -> upto=2   check -> upto=4   run -> upto=3 (+ layer 4, non-blocking)

    `strict` does not change what any layer *finds* — every diagnostic is
    collected either way. It changes only whether warnings block, which is
    `DiagnosticBag.exit_code(strict=...)` at the CLI boundary. It is accepted
    here because §4 freezes this signature and because a layer may one day want
    to consult it (E317 is specced that way).
    """
    bag = DiagnosticBag()
    workflow: Workflow | None = None

    # --- Layer 0: File & encoding checks (Dev D) ---
    from yeet.validation import layer0_file

    bag.extend(layer0_file.check(path))
    if bag.has_errors() or upto < 1:
        return bag, workflow

    # --- Layer 1: YAML syntax, duplicate keys, the `on:`-is-True trap (Dev A) ---
    from yeet.validation import layer1_yaml

    bag1, data = layer1_yaml.check(path)
    bag.extend(bag1)
    if bag.has_errors() or data is None or upto < 2:
        return bag, workflow

    # --- Dialect: rewrite `vibe`/`the_grind`/`moves`/... to canonical keys (Dev A) ---
    # In place and position-preserving, so every diagnostic below still points
    # at the line the user actually wrote. Never fails, never warns.
    #
    # Both spellings are accepted in any file in any directory — a dialect file
    # under `.github/workflows/` and a canonical one under `.yeet/flows/` both
    # work, because this pass is keyed on the CONTENT and never on the path.
    # The one thing that cannot be resolved is a mapping that uses both
    # spellings of the same key: the rewrite is a pop-and-reinsert, so one of
    # them would be dropped without a word. E106 refuses instead of guessing.
    from yeet.parser.aliases import normalize

    bag.extend(_collisions(data, path))
    if bag.has_errors():
        return bag, workflow

    data, used_dialect = normalize(data)

    # --- Layer 2: Schema validation (Dev A) ---
    from yeet.validation import layer2_schema

    bag.extend(layer2_schema.check(data, path))
    if bag.has_errors() or upto < 3:
        return bag, workflow

    # --- Parser / Builder: dict -> Workflow IR (Dev A) ---
    workflow = _build(data, path, bag)
    if workflow is None or upto < 3:
        return bag, workflow
    workflow.used_dialect = used_dialect

    # --- Layer 3: Semantic validation (Dev B) ---
    from yeet.validation import layer3_semantic

    bag.extend(layer3_semantic.check(workflow))
    if bag.has_errors() or upto < 4:
        return bag, workflow

    # --- Layer 4: Lint / code standards (Dev D) ---
    # Importing the PACKAGE, not `.base`: the five rule modules self-register on
    # import, and importing `base` alone leaves RULES empty. See the note in
    # layer4_lint/__init__.py.
    from yeet.core.config import load_lint_config
    from yeet.validation.layer4_lint import run_lints

    bag.extend(run_lints(workflow, path, load_lint_config(path.parent)))

    return bag, workflow


def _collisions(data: object, path: Path) -> list[Diagnostic]:
    """E106 — one key, two spellings, in the same mapping."""
    from yeet.parser.aliases import find_collisions

    out: list[Diagnostic] = []
    for hit in find_collisions(data):
        written = " and ".join(f"`{s}`" for s in hit.spellings)
        out.append(
            Diagnostic(
                code="YEET-E106",
                severity=Severity.ERROR,
                message=f"{written} are the same key — `{hit.canonical}` — written twice",
                file=path,
                pos=Position(hit.line, hit.col) if hit.line >= 0 else None,
                help=f"Keep one of them. Both mean `{hit.canonical}`.",
                note="Canonical GitHub Actions syntax and the yeet dialect can be "
                "mixed freely in one file; the same key twice is the exception.",
            )
        )
    return out


def _build(data: object, path: Path, bag: DiagnosticBag) -> Workflow | None:
    """Build the IR, reporting a crash instead of hiding it.

    This used to be `except (NotImplementedError, Exception): workflow = None`,
    which turned any bug in the builder into "your file has no jobs" — the
    single worst failure mode for a validator, because the user goes looking for
    a mistake that is ours. An unexpected exception here is a yeet bug, so it is
    reported as one, with the real message. `YEET_DEBUG=1` re-raises for a
    traceback while developing.
    """
    from yeet.parser.builder import build_workflow

    try:
        return build_workflow(data, path, bag)
    except Exception as exc:  # noqa: BLE001 - deliberate: report, never hide
        if os.environ.get("YEET_DEBUG"):
            raise
        bag.add(
            Diagnostic(
                code="YEET-E900",
                severity=Severity.ERROR,
                message=f"internal error while building the workflow: {exc!r}",
                file=path,
                help="This is a bug in yeet, not in your file. "
                "Re-run with YEET_DEBUG=1 for a traceback and please report it.",
            )
        )
        return None
