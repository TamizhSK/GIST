#!/usr/bin/env python3
"""
bootstrap.py — creates the full `yeet` project skeleton.

╔══════════════════════════════════════════════════════════════════════════╗
║  HISTORICAL ARTIFACT — DO NOT RE-RUN.                                    ║
║                                                                          ║
║  This script generated the skeleton once. That skeleton is now in the    ║
║  repo, and it has moved on:                                              ║
║                                                                          ║
║    * the stubs embedded below still carry the PRE-DAY-0 signatures       ║
║      (discover_flows -> list[Path], normalize(node) -> object,           ║
║       validate_file(...) -> DiagnosticBag). plan.md §4 is authoritative. ║
║    * it still writes secrets/masking.py, which ADR 0007 deleted.         ║
║    * it does not know about core/{masking,events,project,graph}.py       ║
║      and writes the pre-ADR-0007 import-linter contract.                 ║
║                                                                          ║
║  It skips files that already exist, so a plain run is merely useless —   ║
║  but `--force` WILL revert Day 0. Clone the repo instead.                ║
║                                                                          ║
║  Kept because it documents how the tree was laid out, and because the    ║
║  layout argument is worth a slide. If you ever regenerate from it, diff  ║
║  the result against HEAD before committing anything.                     ║
╚══════════════════════════════════════════════════════════════════════════╝

Works on Windows, macOS, Linux and WSL. Only uses the stdlib.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PKG = "yeet"  # <-- change this one constant to rename the whole tool


# ---------------------------------------------------------------------------
# 1. REAL FILES — content that matters on Day 0
# ---------------------------------------------------------------------------

REAL: dict[str, str] = {}

REAL["pyproject.toml"] = f'''\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{PKG}"
version = "0.1.0"
description = "A local GitHub Actions-compatible runner with a dialect of its own"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13.7",
    "ruamel.yaml>=0.18",
    "pydantic>=2.7",
    "jsonschema>=4.22",
    "docker>=7.1",
    "watchdog>=4.0",
    "platformdirs>=4.2",
    "pathspec>=0.12",
    "cryptography>=42.0",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-cov",
    "ruff>=0.4",
    "mypy>=1.10",
    "import-linter>=2.0",
    "pre-commit>=3.7",
]

[project.scripts]
{PKG} = "{PKG}.cli.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/{PKG}"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "docker: needs a running Docker daemon",
    "slow: takes more than a second",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "PTH"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src"]

# --- Architecture enforcement: the tier rule from docs/architecture.md -------
# Run with:  lint-imports
[tool.importlinter]
root_package = "{PKG}"

[[tool.importlinter.contracts]]
name = "Layered architecture (a module may only import from lower tiers)"
type = "layers"
layers = [
    "{PKG}.cli",
    "{PKG}.triggers",
    "{PKG}.executor | {PKG}.actions | {PKG}.storage | {PKG}.secrets",
    "{PKG}.planner",
    "{PKG}.validation",
    "{PKG}.parser | {PKG}.analyzer",
    "{PKG}.expressions | {PKG}.reporting",
    "{PKG}.core",
]

[[tool.importlinter.contracts]]
name = "core is a leaf — it imports nothing from us"
type = "forbidden"
source_modules = ["{PKG}.core"]
forbidden_modules = [
    "{PKG}.cli", "{PKG}.analyzer", "{PKG}.parser", "{PKG}.validation",
    "{PKG}.expressions", "{PKG}.planner", "{PKG}.executor", "{PKG}.actions",
    "{PKG}.reporting", "{PKG}.secrets", "{PKG}.storage", "{PKG}.triggers",
]
'''

REAL[".gitignore"] = f'''\
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# {PKG} runtime state — never commit
.{PKG}/tmp/
.{PKG}/runs/
.{PKG}/artifacts/
.{PKG}/.secrets
.{PKG}/.secrets.key
'''

REAL[".gitattributes"] = '''\
* text=auto eol=lf
*.png binary
*.jpg binary

# Step scripts MUST be LF or bash inside the container dies with $'\\r'
*.sh text eol=lf
src/**/templates/** text eol=lf
tests/fixtures/** text eol=lf
tests/invalid/** text eol=lf
'''

REAL[".editorconfig"] = '''\
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
trim_trailing_whitespace = true

[*.py]
indent_size = 4

[*.{yml,yaml,json}]
indent_size = 2
'''

REAL[".pre-commit-config.yaml"] = '''\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: mixed-line-ending
        args: [--fix=lf]
      - id: check-yaml
      - id: check-merge-conflict
'''

REAL[".github/workflows/ci.yml"] = f'''\
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    # The joke that is also the test strategy: we use real GitHub Actions
    # to prove our GitHub Actions clone works on all three platforms.
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.12"]
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python }}}}
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: lint-imports
      - run: pytest -m "not docker" --cov={PKG}
'''

REAL["src/PKG/core/diagnostics.py"] = '''\
"""FROZEN CONTRACT #1 — the diagnostic type.

Every subsystem emits these. Only `reporting` renders them.
Nobody calls print() for an error. Ever.

Owner: whole team (changes need everyone's sign-off)
Tier: 0 — imports nothing from this package
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"      # blocks execution
    WARNING = "warning"  # blocks only under --strict
    INFO = "info"        # never blocks

    @property
    def rank(self) -> int:
        return {"error": 2, "warning": 1, "info": 0}[self.value]


@dataclass(frozen=True, slots=True)
class Position:
    """0-indexed line, 0-indexed column. Rendered as 1-indexed."""
    line: int
    col: int
    end_col: int | None = None

    @classmethod
    def unknown(cls) -> "Position":
        return cls(line=-1, col=-1)

    @property
    def is_known(self) -> bool:
        return self.line >= 0


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str                       # "YEET-E301"
    severity: Severity
    message: str                    # one line, plain language, no jargon
    file: Path | None = None
    pos: Position | None = None
    help: str | None = None         # "did you mean `build`?"
    note: str | None = None         # extra context, optional
    url: str | None = None          # docs/rules.md#yeet-e301

    def __str__(self) -> str:       # fallback if the renderer ever fails
        loc = ""
        if self.file:
            loc = str(self.file)
            if self.pos and self.pos.is_known:
                loc += f":{self.pos.line + 1}:{self.pos.col + 1}"
            loc += ": "
        return f"{loc}{self.severity.value}[{self.code}] {self.message}"


@dataclass
class DiagnosticBag:
    """Collect-don't-raise. Validation layers append; the pipeline decides."""
    items: list[Diagnostic] = field(default_factory=list)

    def add(self, d: Diagnostic) -> None:
        self.items.append(d)

    def extend(self, ds: "list[Diagnostic] | DiagnosticBag") -> None:
        self.items.extend(ds.items if isinstance(ds, DiagnosticBag) else ds)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.WARNING]

    def has_errors(self) -> bool:
        return bool(self.errors)

    def exit_code(self, strict: bool = False) -> int:
        if self.errors:
            return 2
        if strict and self.warnings:
            return 2
        return 0

    def sorted(self) -> list[Diagnostic]:
        """Group by file, then by position, so the report reads top-to-bottom."""
        def key(d: Diagnostic):
            return (
                str(d.file or ""),
                d.pos.line if d.pos and d.pos.is_known else 1 << 30,
                d.pos.col if d.pos and d.pos.is_known else 0,
                d.code,
            )
        return sorted(self.items, key=key)

    def __len__(self) -> int:
        return len(self.items)
'''

REAL["src/PKG/core/ir.py"] = '''\
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
    name: str | None = None              # vibe:
    id: str | None = None
    run: str | None = None               # bet:      \\ exactly
    uses: str | None = None              # yoink:    / one of these
    with_: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)   # drip:
    if_: str | None = None               # only_if:
    shell: str | None = None
    working_directory: str | None = None
    continue_on_error: bool = False      # delulu:
    timeout_minutes: int | None = None   # patience:
    key_pos: dict[str, Position] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name or self.run or self.uses or "<unnamed step>"


@dataclass
class Strategy:
    pos: Position
    matrix: dict[str, list[Any]] = field(default_factory=dict)   # multiverse:
    include: list[dict[str, Any]] = field(default_factory=list)
    exclude: list[dict[str, Any]] = field(default_factory=list)
    fail_fast: bool = True
    max_parallel: int | None = None


@dataclass
class Job:
    key: str                             # the mapping key: `build`
    pos: Position
    name: str | None = None
    runs_on: str | None = None           # cooked_on:
    needs: list[str] = field(default_factory=list)      # after:
    steps: list[Step] = field(default_factory=list)     # moves:
    env: dict[str, str] = field(default_factory=dict)
    if_: str | None = None
    strategy: Strategy | None = None     # squad:
    container_image: str | None = None
    dockerfile: str | None = None
    timeout_minutes: int | None = None
    outputs: dict[str, str] = field(default_factory=dict)
    key_pos: dict[str, Position] = field(default_factory=dict)


@dataclass
class Trigger:
    event: str                           # "push", "manual", ...
    pos: Position
    filters: dict[str, Any] = field(default_factory=dict)   # branches, paths...


@dataclass
class Workflow:
    source: Path
    pos: Position
    name: str | None = None              # vibe:
    triggers: list[Trigger] = field(default_factory=list)   # when: / on:
    jobs: dict[str, Job] = field(default_factory=dict)       # the_grind:
    env: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    raw: Any = None                      # the ruamel tree, for the renderer
    used_dialect: bool = False           # True if any Gen-Z alias was seen

    @property
    def display_name(self) -> str:
        return self.name or self.source.name
'''

REAL["src/PKG/core/codes.py"] = '''\
"""The diagnostic code registry — single source of truth.

Adding a rule = add a row here + implement it + add tests/invalid/<CODE>.yml.
docs/rules.md is GENERATED from this table, so it can never drift.

Ranges:  E0xx file · E1xx yaml · E2xx schema · E3xx semantic · W4xx lint · I4xx info

Owner: Dev D (but everyone adds rows)
Tier: 0
"""
from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Severity

PREFIX = "YEET"


@dataclass(frozen=True, slots=True)
class Rule:
    code: str
    default_severity: Severity
    title: str
    layer: int


def _e(code: str, title: str, layer: int) -> Rule:
    return Rule(f"{PREFIX}-{code}", Severity.ERROR, title, layer)


def _w(code: str, title: str, layer: int) -> Rule:
    return Rule(f"{PREFIX}-{code}", Severity.WARNING, title, layer)


# Seed set. Fill the rest in from docs/architecture.md §3.10 as you implement.
RULES: dict[str, Rule] = {r.code: r for r in [
    # Layer 0 — file & encoding
    _e("E002", "file is empty", 0),
    _e("E005", "tabs used for indentation", 0),
    _w("W006", "CRLF line endings", 0),
    # Layer 1 — yaml
    _e("E101", "YAML parse failure", 1),
    _e("E102", "duplicate key", 1),
    _e("E103", "top-level document is not a mapping", 1),
    _w("W105", "unquoted `on` parsed as a boolean", 1),
    # Layer 2 — schema
    _e("E201", "unknown key", 2),
    _e("E202", "required key missing", 2),
    _e("E204", "step has both `run` and `uses`", 2),
    _e("E205", "step has neither `run` nor `uses`", 2),
    # Layer 3 — semantic
    _e("E301", "`needs` references an unknown job", 3),
    _e("E302", "dependency cycle", 3),
    _e("E309", "expression fails to parse", 3),
    # Layer 4 — lint / standards
    _w("W401", "missing name", 4),
    _w("W402", "action pinned to a moving ref", 4),
    _w("W404", "possible hardcoded secret", 4),
    _w("W407", "job has no timeout", 4),
]}


def get(code: str) -> Rule:
    key = code if code.startswith(PREFIX) else f"{PREFIX}-{code}"
    if key not in RULES:
        raise KeyError(f"unregistered diagnostic code: {code}")
    return RULES[key]
'''

REAL["src/PKG/core/result.py"] = '''\
"""Execution result types. The executor produces these; reporting renders them.

Owner: Dev C + Dev D
Tier: 0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "cooked"
    SUCCESS = "slayed"
    FAILURE = "flopped"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self not in (Status.PENDING, Status.RUNNING)

    @property
    def ok(self) -> bool:
        return self in (Status.SUCCESS, Status.SKIPPED)


@dataclass
class StepResult:
    step_name: str
    status: Status = Status.PENDING
    exit_code: int | None = None
    duration_s: float = 0.0
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResult:
    job_key: str
    matrix_leg: dict[str, object] = field(default_factory=dict)
    status: Status = Status.PENDING
    steps: list[StepResult] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    duration_s: float = 0.0


@dataclass
class RunResult:
    run_id: str
    workflow_name: str
    jobs: list[JobResult] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def status(self) -> Status:
        if any(j.status is Status.FAILURE for j in self.jobs):
            return Status.FAILURE
        if all(j.status.ok for j in self.jobs):
            return Status.SUCCESS
        return Status.FAILURE

    @property
    def exit_code(self) -> int:
        return 0 if self.status is Status.SUCCESS else 1
'''

REAL["src/PKG/parser/aliases.yml"] = '''\
# The dialect. LEFT = what users may write, RIGHT = canonical GitHub Actions key.
#
# Architectural rule: there is exactly ONE parser. It parses canonical GitHub
# Actions syntax. This table is applied as a key-rewrite pass immediately after
# YAML load, which is why real .github/workflows files keep working unchanged.
#
# Add aliases freely — it costs one line and zero code.

keys:
  vibe: name
  when: "on"
  the_grind: jobs
  missions: jobs
  cooked_on: runs-on
  moves: steps
  bet: run
  cook: run
  yoink: uses
  borrow: uses
  after: needs
  waits_for: needs
  only_if: if
  no_cap_if: if
  drip: env
  tea: secrets
  squad: strategy
  multiverse: matrix
  loot: artifacts
  stash: cache
  patience: timeout-minutes
  delulu: continue-on-error
  its_fine: continue-on-error
  where: working-directory
  manual: workflow_dispatch     # event name, not a key — handled in builder.py

status:
  success: slayed
  failure: flopped
  partial: mid
  running: cooked
  skipped: "skipped (not the vibe)"
'''

REAL["README.md"] = f'''\
# {PKG}

A local, GitHub Actions-compatible workflow runner — with a dialect of its own.

Point it at any project (cloned from GitHub or created locally). It finds the
workflow files, tells you whether they're written correctly, and runs them in
Docker on your machine.

```bash
{PKG} scan .        # what is this project, and what flows does it have?
{PKG} check .       # is the .yml written correctly?  (5 validation layers)
{PKG} run           # run it in Docker
```

## Status

Day 0 skeleton. See `docs/architecture.md` for the design and
`docs/rules.md` for the diagnostic code registry.

## Development

```bash
python -m venv .venv
# Linux/macOS/WSL:
source .venv/bin/activate
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1

pip install -e ".[dev]"
pre-commit install

pytest -m "not docker"     # unit tests, no Docker needed
lint-imports               # enforces the tier rule
{PKG} --help
```

## Non-goals

See `docs/architecture.md` §9. We say no on purpose.
'''

REAL["docs/adr/0001-record-architecture-decisions.md"] = '''\
# ADR 0001 — We record architecture decisions

## Status
Accepted

## Context
Four people are building one system in a week. Decisions made in a hallway
conversation get re-litigated on Thursday when someone hits a wall.

## Decision
Every choice that affects more than one subsystem gets a numbered file in
`docs/adr/`. One page: Context, Decision, Consequences. No approval process —
write it, link it in the PR.

## Consequences
Costs ten minutes each. Gives us the "why" section of the final presentation
for free, and stops the same argument happening twice.

---

## ADRs to write in week one
- 0002 — Why Python and not Go
- 0003 — Why one parser plus an alias table, not two parsers
- 0004 — Why one container per job with exec-per-step
- 0005 — Why validation is a five-layer pipeline that gates execution
- 0006 — Why ruamel.yaml over PyYAML (position data)
'''


# ---------------------------------------------------------------------------
# 2. STUB MODULES — (path, owner, tier, purpose, body)
# ---------------------------------------------------------------------------

S = tuple[str, str, str, str, str]

STUBS: list[S] = [
    # ---- core -------------------------------------------------------------
    ("core/config.py", "Dev D", "0",
     "Runtime config + per-platform paths (platformdirs). Loaded once, passed down.",
     'def config_dir() -> Path:\n    """~/.config/yeet, %APPDATA%\\\\yeet, ~/Library/... — use platformdirs."""\n    raise NotImplementedError\n'),
    ("core/exceptions.py", "Dev D", "0",
     "Exceptions for *bugs*, not for user errors. User errors are Diagnostics.",
     'class YeetInternalError(Exception):\n    """Something we did wrong. Never shown raw to the user."""\n'),

    # ---- analyzer (Dev A) -------------------------------------------------
    ("analyzer/project.py", "Dev A", "2",
     "Project dataclass + analyze(path) -> Project. The public face of this package.",
     'def analyze(start: Path) -> "Project":\n    """Root detection -> discovery -> fingerprint. See architecture.md 3.9."""\n    raise NotImplementedError\n'),
    ("analyzer/root.py", "Dev A", "2",
     "Walk UPWARD for .git / .yeet / .github/workflows / any ecosystem manifest.",
     'def find_root(start: Path) -> Path:\n    """Stop at filesystem root or $HOME. Never shell out to git."""\n    raise NotImplementedError\n'),
    ("analyzer/discover.py", "Dev A", "2",
     "Walk DOWNWARD for flow files. Exclude list + depth cap + inode set + PermissionError.",
     'MAX_DEPTH = 5\nMAX_FILES = 20_000\nFOLLOW_SYMLINKS = False\n\nEXCLUDE_DIRS = {\n    ".git", "node_modules", "vendor", "dist", "build", "target", "out",\n    ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",\n    ".gradle", ".next", ".nuxt", "bin", "obj",\n}\n\n\ndef discover_flows(root: Path) -> list[Path]:\n    raise NotImplementedError\n'),
    ("analyzer/fingerprint.py", "Dev A", "2",
     "Detect the stack from marker files so we can pick an image / generate a flow.",
     'def fingerprint(root: Path) -> list["Ecosystem"]:\n    raise NotImplementedError\n'),
    ("analyzer/markers.py", "Dev A", "2",
     "DATA ONLY: marker file -> ecosystem -> suggested image + default commands.",
     'MARKERS = {\n    "package.json": ("node", "node:20", ["npm ci", "npm test"]),\n    "pyproject.toml": ("python", "python:3.12", ["pip install -e .", "pytest"]),\n    "go.mod": ("go", "golang:1.22", ["go build ./...", "go test ./..."]),\n    # ... fill from architecture.md 3.9 step 3\n}\n'),

    # ---- parser (Dev A) ---------------------------------------------------
    ("parser/loader.py", "Dev A", "2",
     "ruamel.yaml round-trip load. Emits E101/E102/E103/W105. KEEPS line+col.",
     'def load_with_positions(path: Path, bag: DiagnosticBag) -> object | None:\n    """YAML(typ=\'rt\'); use .lc.key()/.lc.value() for every position."""\n    raise NotImplementedError\n'),
    ("parser/aliases.py", "Dev A", "2",
     "Load aliases.yml; rewrite dialect keys to canonical ones. Sets used_dialect.",
     'def normalize(node: object) -> object:\n    """Recursive key rewrite. Preserves ruamel position data — do not rebuild dicts naively."""\n    raise NotImplementedError\n'),
    ("parser/builder.py", "Dev A", "2",
     "Normalized dict tree -> IR dataclasses. Attaches a Position to every node.",
     'def build_workflow(data: object, source: Path, bag: DiagnosticBag) -> "Workflow | None":\n    raise NotImplementedError\n'),

    # ---- validation -------------------------------------------------------
    ("validation/pipeline.py", "Dev D", "3",
     "Runs layers 0-4 in order. Stops BETWEEN layers on error, not within one.",
     'def validate_file(path: Path, *, strict: bool = False, upto: int = 4) -> DiagnosticBag:\n    """layer0 -> layer1 -> layer2 -> layer3 -> layer4. Return everything found."""\n    raise NotImplementedError\n'),
    ("validation/layer0_file.py", "Dev D", "3",
     "File & encoding: empty, non-UTF8, BOM, TAB indentation, CRLF, absurd size.",
     'def check(path: Path) -> DiagnosticBag:\n    raise NotImplementedError\n'),
    ("validation/layer1_yaml.py", "Dev A", "3",
     "YAML syntax + duplicate keys + the `on:`-is-True trap.",
     'def check(path: Path) -> tuple[DiagnosticBag, object | None]:\n    raise NotImplementedError\n'),
    ("validation/layer2_schema.py", "Dev A", "3",
     "jsonschema against workflow.schema.json; best_match + readable JSON paths.",
     'def check(data: object, path: Path) -> DiagnosticBag:\n    raise NotImplementedError\n'),
    ("validation/layer3_semantic.py", "Dev B", "3",
     "Cross-reference checks over the IR: needs, cycles, step ids, contexts, matrix vars.",
     'def check(wf: "Workflow") -> DiagnosticBag:\n    """E301 E302 E303 E305-E317. Reuses planner.graph for cycle detection."""\n    raise NotImplementedError\n'),
    ("validation/suggest.py", "Dev A", "3",
     "difflib did-you-mean against canonical keys AND dialect aliases.",
     'def did_you_mean(word: str, candidates: "Iterable[str]") -> str | None:\n    raise NotImplementedError\n'),
    ("validation/layer4_lint/base.py", "Dev D", "3",
     "Rule protocol + registry + .yeet/lint.yml severity overrides.",
     'RULES: list["LintRule"] = []\n\n\ndef register(rule: "LintRule") -> "LintRule":\n    RULES.append(rule)\n    return rule\n'),
    ("validation/layer4_lint/naming.py", "Dev D", "3", "W401, I415.", ""),
    ("validation/layer4_lint/pinning.py", "Dev D", "3", "W402, W403, W412.", ""),
    ("validation/layer4_lint/secrets_scan.py", "Dev D", "3",
     "W404 — regex + Shannon entropy. The highest-value rule in the tool.",
     'def shannon_entropy(s: str) -> float:\n    raise NotImplementedError\n'),
    ("validation/layer4_lint/shell.py", "Dev D", "3", "W405, W406.", ""),
    ("validation/layer4_lint/portability.py", "Dev D", "3", "W409, W410 — the cross-platform rules.", ""),

    # ---- expressions (Dev B) ---------------------------------------------
    ("expressions/lexer.py", "Dev B", "1", "Tokenize ${{ }} contents. Track offsets for E309.", ""),
    ("expressions/ast_nodes.py", "Dev B", "1", "AST node dataclasses.", ""),
    ("expressions/parser.py", "Dev B", "1",
     "Pratt parser. NEVER eval(). Raises ExprSyntaxError with an offset.",
     'def parse(src: str) -> "Node":\n    raise NotImplementedError\n'),
    ("expressions/evaluator.py", "Dev B", "1",
     "Walk the AST. Replicate GitHub's loose equality ('1' == 1 is true).",
     'def evaluate(node: "Node", ctx: "Contexts") -> object:\n    raise NotImplementedError\n'),
    ("expressions/functions.py", "Dev B", "1",
     "contains, startsWith, endsWith, format, join, toJSON, fromJSON, hashFiles, success/failure/always/cancelled.",
     'def hash_files(patterns: list[str], root: Path) -> str:\n    """SORT the glob results before hashing or you get different hashes per OS."""\n    raise NotImplementedError\n'),
    ("expressions/contexts.py", "Dev B", "1",
     "github, env, job, steps, runner, matrix, needs, secrets, inputs, vars.",
     'def build_github_context(root: Path, event: str) -> dict[str, object]:\n    raise NotImplementedError\n'),

    # ---- planner (Dev B) --------------------------------------------------
    ("planner/matrix.py", "Dev B", "4", "Expand strategy.matrix -> concrete legs. include AFTER exclude order matters.", ""),
    ("planner/graph.py", "Dev B", "4",
     "Build the DAG, detect cycles (report the cycle path), topo-sort into waves.",
     'def topo_waves(jobs: dict[str, "Job"]) -> list[list[str]]:\n    raise NotImplementedError\n\n\ndef find_cycle(jobs: dict[str, "Job"]) -> list[str] | None:\n    """Return the cycle as a path so E302 can print build -> test -> build."""\n    raise NotImplementedError\n'),
    ("planner/plan.py", "Dev B", "4", "Workflow -> ExecutionPlan (waves of concrete job instances).", ""),

    # ---- executor (Dev C) -------------------------------------------------
    ("executor/backend.py", "Dev C", "5",
     "Protocol both backends implement. Keeps Docker out of everyone else's imports.",
     'class Backend(Protocol):\n    def run_job(self, job: "Job", ctx: object) -> "JobResult": ...\n'),
    ("executor/docker_backend.py", "Dev C", "5",
     "ONE container per job, exec per step. Never docker-run per step.",
     'KEEPALIVE_CMD = ["tail", "-f", "/dev/null"]\n\n\nclass DockerBackend:\n    def run_job(self, job, ctx):\n        raise NotImplementedError\n'),
    ("executor/local_backend.py", "Dev C", "5", "runs-on: local — host shell. bash, or pwsh on Windows.", ""),
    ("executor/images.py", "Dev C", "5", "runs-on value -> image name. ubuntu-latest -> our base image.", ""),
    ("executor/build.py", "Dev C", "5",
     "docker build for a project Dockerfile. Tag = hash(dockerfile + context) = free cache.",
     'def build_tag(dockerfile: Path) -> str:\n    raise NotImplementedError\n'),
    ("executor/workspace.py", "Dev C", "5", "Bind mount, /workspace layout, temp script dir.", ""),
    ("executor/paths.py", "Dev C", "5",
     "THE cross-platform helper. C:\\\\x -> /c/x. Unit-test this on all 3 OSes.",
     'def to_container_path(host: Path) -> str:\n    raise NotImplementedError\n'),
    ("executor/platform_.py", "Dev C", "5",
     "OS + WSL detection, docker socket discovery, /mnt/c slowness warning.",
     'def is_wsl() -> bool:\n    """/proc/version contains \'microsoft\'."""\n    raise NotImplementedError\n'),
    ("executor/state_files.py", "Dev C", "5",
     "GITHUB_ENV / GITHUB_OUTPUT / GITHUB_PATH / GITHUB_STEP_SUMMARY read-back.",
     'def read_back(step_dir: Path) -> dict[str, dict[str, str]]:\n    """Each step is a NEW PROCESS. This file dance is the only way state survives."""\n    raise NotImplementedError\n'),
    ("executor/commands.py", "Dev C", "5", "Parse ::group:: ::error:: ::add-mask:: etc from stdout.", ""),
    ("executor/script.py", "Dev C", "5",
     "Write a step's script to disk. ALWAYS LF — CRLF kills bash in the container.",
     'def write_step_script(text: str, dest: Path) -> None:\n    dest.write_bytes(text.replace("\\r\\n", "\\n").encode("utf-8"))\n'),

    # ---- actions ----------------------------------------------------------
    ("actions/resolver.py", "Dev A", "5", "uses: -> local path | remote clone | docker. Cache under ~/.yeet/actions.", ""),
    ("actions/composite.py", "Dev A", "5", "runs.using: composite — inline the steps. Tier 1, do this first.", ""),
    ("actions/docker_action.py", "Dev C", "5", "runs.using: docker.", ""),
    ("actions/js_action.py", "Dev C", "5", "runs.using: node20 — INPUT_* env vars, node dist/index.js.", ""),

    # ---- reporting (Dev D) ------------------------------------------------
    ("reporting/render.py", "Dev D", "1",
     "THE code-frame renderer. rustc/eslint style. Must never itself crash.",
     'CONTEXT_BEFORE = 2\nCONTEXT_AFTER = 1\n\n\ndef render_diagnostics(bag: "DiagnosticBag", *, color: bool = True) -> str:\n    """Clamp every index. Wrap in try/except and fall back to str(diagnostic)."""\n    raise NotImplementedError\n'),
    ("reporting/console.py", "Dev D", "1", "Live rich tree for a run: jobs, steps, timings, status glyphs.", ""),
    ("reporting/json_out.py", "Dev D", "1", "--format json.", ""),
    ("reporting/sarif.py", "Dev D", "1", "--format sarif (2.1.0). VS Code + GitHub code scanning read it free.", ""),
    ("reporting/theme.py", "Dev D", "1", "Colors, glyphs, the status vocabulary. Honor NO_COLOR.", ""),

    # ---- secrets / storage / triggers (Dev D) -----------------------------
    ("secrets/store.py", "Dev D", "5", "Encrypted local store (Fernet + scrypt). Precedence: flag > file > keyring > .env.", ""),
    ("secrets/masking.py", "Dev D", "5",
     "Filter EVERY output line. Mask base64 and url-encoded variants too.",
     'def mask(line: str, secrets: set[str]) -> str:\n    raise NotImplementedError\n'),
    ("storage/runs.py", "Dev D", "5", "JSONL run logs under .yeet/runs/<run-id>/. Powers `yeet logs`.", ""),
    ("storage/artifacts.py", "Dev D", "5", "loot: upload/download -> .yeet/artifacts/<run-id>/.", ""),
    ("storage/cache.py", "Dev D", "5", "stash: keyed tarballs + restore-keys prefix matching.", ""),
    ("triggers/watcher.py", "Dev D", "6",
     "watchdog daemon. DEBOUNCE or a run's own writes retrigger it forever.",
     'DEBOUNCE_MS = 500\n'),
    ("triggers/hooks.py", "Dev D", "6", "Write .git/hooks/post-commit + pre-push shims, chmod 0o755.", ""),
    ("triggers/events.py", "Dev D", "6", "Event objects + matching against a workflow's triggers.", ""),

    # ---- cli --------------------------------------------------------------
    ("cli/app.py", "Dev A", "7",
     "Typer app. Wires subcommands. Owns exit codes: 0 ok, 1 job failed, 2 bad file, 3 no docker.",
     'import typer\n\napp = typer.Typer(no_args_is_help=True, add_completion=False)\n\n\ndef main() -> None:\n    app()\n\n\nif __name__ == "__main__":\n    main()\n'),
    ("cli/cmd_scan.py", "Dev A", "7", "yeet scan — analyzer output + a fast layer 0-2 summary per flow.", ""),
    ("cli/cmd_check.py", "Dev D", "7", "yeet check — the full 5 layers. --strict, --format json|sarif.", ""),
    ("cli/cmd_run.py", "Dev C", "7", "yeet run — validate (L0-L3), refuse on error, then plan + execute.", ""),
    ("cli/cmd_init.py", "Dev A", "7", "yeet init [--auto] — scaffold a flow from the fingerprint.", ""),
    ("cli/cmd_watch.py", "Dev D", "7", "yeet watch — the daemon.", ""),
    ("cli/cmd_graph.py", "Dev B", "7", "yeet graph — ASCII DAG. 30 lines, big demo payoff.", ""),
    ("cli/cmd_logs.py", "Dev D", "7", "yeet logs <run-id> — replay JSONL.", ""),
    ("cli/cmd_secrets.py", "Dev D", "7", "yeet secrets set/list/rm.", ""),
    ("cli/cmd_hooks.py", "Dev D", "7", "yeet hooks install/uninstall.", ""),
    ("cli/cmd_explain.py", "Dev D", "7", "yeet explain YEET-E301 — print that section of docs/rules.md.", ""),
]

TIER_IMPORTS = {
    "0": "nothing (core is a leaf)",
    "1": "core",
    "2": "core, expressions, reporting",
    "3": "core, expressions, reporting, parser, analyzer",
    "4": "core, expressions, reporting, parser, analyzer, validation",
    "5": "everything below tier 5",
    "6": "everything below tier 6",
    "7": "anything",
}

EMPTY_DIRS = [
    "docs/adr",
    "src/PKG/parser/schema",
    "src/PKG/templates/hooks",
    "tests/fixtures/valid",
    "tests/invalid",
    "tests/corpus",
    "tests/e2e",
    "tests/unit",
]

PACKAGES = [
    "core", "analyzer", "parser", "validation", "validation/layer4_lint",
    "expressions", "planner", "executor", "actions", "reporting",
    "secrets", "storage", "triggers", "cli",
]


def stub_text(path: str, owner: str, tier: str, purpose: str, body: str) -> str:
    header = (
        f'"""{purpose}\n\n'
        f"Owner: {owner}\n"
        f"Tier: {tier} — may import from: {TIER_IMPORTS[tier]}\n"
        f"See docs/architecture.md\n"
        f'"""\n'
        f"from __future__ import annotations\n"
    )
    return header + ("\n" + body if body.strip() else "")


def write(base: Path, rel: str, text: str, force: bool) -> str:
    rel = rel.replace("PKG", PKG)
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return f"  skip   {rel}"
    # newline="\n" — never emit CRLF, even when this runs on Windows
    dest.write_text(text, encoding="utf-8", newline="\n")
    return f"  create {rel}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--into", default=f"./{PKG}")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    base = Path(args.into).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    print(f"scaffolding {PKG} into {base}\n")

    lines: list[str] = []

    for rel, text in REAL.items():
        lines.append(write(base, rel, text, args.force))

    for pkg in PACKAGES:
        rel = f"src/PKG/{pkg}/__init__.py"
        lines.append(write(base, rel, "", args.force))
    lines.append(write(base, "src/PKG/__init__.py",
                       '__all__ = ["__version__"]\n__version__ = "0.1.0"\n', args.force))
    lines.append(write(base, "src/PKG/__main__.py",
                       f"from {PKG}.cli.app import main\n\nmain()\n", args.force))

    for rel, owner, tier, purpose, body in STUBS:
        lines.append(write(base, f"src/PKG/{rel}", stub_text(rel, owner, tier, purpose, body), args.force))

    lines.append(write(base, "tests/conftest.py",
                       "import pytest\n\n\n@pytest.fixture\ndef fixtures_dir():\n"
                       "    from pathlib import Path\n    return Path(__file__).parent / \"fixtures\"\n",
                       args.force))
    lines.append(write(base, "tests/invalid/README.md",
                       "One file per diagnostic code, named after the code it must produce.\n"
                       "`E301.yml` must emit exactly {YEET-E301}. One parametrized test covers them all.\n",
                       args.force))

    for d in EMPTY_DIRS:
        (base / d.replace("PKG", PKG)).mkdir(parents=True, exist_ok=True)
        gk = base / d.replace("PKG", PKG) / ".gitkeep"
        if not gk.exists():
            gk.write_text("", encoding="utf-8")

    created = sum(1 for line in lines if line.strip().startswith("create"))
    skipped = len(lines) - created
    for line in lines:
        print(line)
    print(f"\n{created} files created, {skipped} skipped.")
    print(f"""
next:
  cd {base}
  git init && git add -A && git commit -m "chore: day 0 skeleton"
  python -m venv .venv && . .venv/bin/activate    # Windows: .venv\\Scripts\\Activate.ps1
  pip install -e ".[dev]"
  pre-commit install
  {PKG} --help
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())