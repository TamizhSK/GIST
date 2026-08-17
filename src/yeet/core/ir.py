"""FROZEN CONTRACT #2 — the intermediate representation.

The parser produces this. Everything downstream consumes it and nothing
else. If you need a new field, raise it in standup — do NOT add it on your
branch, because four people are importing this module.

Every node carries a Position. That is not optional and it cannot be
retrofitted later: diagnostics without line numbers are useless, and the
day you try to add them is the day you rewrite the parser.

Owner: whole team (changes need everyone's sign-off)
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .diagnostics import Position


@dataclass
class Step:
    pos: Position
    name: str | None = None  # vibe:
    id: str | None = None
    run: str | None = None  # bet:      \ exactly
    uses: str | None = None  # yoink:    / one of these
    with_: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)  # drip:
    if_: str | None = None  # only_if:
    shell: str | None = None
    working_directory: str | None = None
    continue_on_error: bool = False  # delulu:
    timeout_minutes: int | None = None  # patience:
    key_pos: dict[str, Position] = field(default_factory=dict)
    action_inputs: dict[str, str] | None = None
    """The `inputs` context for a step INLINED FROM A COMPOSITE ACTION.

    None for a step written in the workflow, and that is the distinction that
    matters: `${{ inputs.x }}` inside a composite action means the ACTION's
    input, and once the steps are inlined nothing else can tell them apart. It
    travels on the step because `INPUT_X` in the env — which did work — only
    ever reached `$INPUT_X` in a shell, so the expression form silently
    resolved to an empty string. Two spellings of one value, one of them a
    lie."""

    @property
    def display_name(self) -> str:
        return self.name or self.run or self.uses or "<unnamed step>"


@dataclass
class Strategy:
    pos: Position
    matrix: dict[str, list[Any]] = field(default_factory=dict)  # multiverse:
    include: list[dict[str, Any]] = field(default_factory=list)
    exclude: list[dict[str, Any]] = field(default_factory=list)
    fail_fast: bool = True
    max_parallel: int | None = None


@dataclass
class Job:
    key: str  # the mapping key: `build`
    pos: Position
    name: str | None = None
    runs_on: str | None = None  # cooked_on:
    needs: list[str] = field(default_factory=list)  # after:
    steps: list[Step] = field(default_factory=list)  # moves:
    env: dict[str, str] = field(default_factory=dict)
    if_: str | None = None
    strategy: Strategy | None = None  # squad:
    container_image: str | None = None
    dockerfile: str | None = None
    timeout_minutes: int | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    key_pos: dict[str, Position] = field(default_factory=dict)


@dataclass
class Trigger:
    event: str  # "push", "manual", ...
    pos: Position
    filters: dict[str, Any] = field(default_factory=dict)  # branches, paths...


@dataclass
class Workflow:
    source: Path
    pos: Position
    name: str | None = None  # vibe:
    triggers: list[Trigger] = field(default_factory=list)  # when: / on:
    jobs: dict[str, Job] = field(default_factory=dict)  # the_grind:
    env: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    raw: Any = None  # the ruamel tree, for the renderer
    used_dialect: bool = False  # True if any Gen-Z alias was seen

    @property
    def display_name(self) -> str:
        return self.name or self.source.name
