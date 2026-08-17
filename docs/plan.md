# yeet — Implementation Plan

**Audience:** the four developers building this. **Purpose:** so that on Monday
morning each person opens the exact files they own and knows what "done" means
for each one, without a meeting.

**Read order:** §0 (what is already done) → §1 (where we actually are) → §3 (the
decisions that were made for you, and why) → §4 (the contract sheet you code
against) → your own section in §5.

Paths in this document are relative to `yeet/` unless stated otherwise.

---

## 0. Status — §2 and §3 are DONE, on disk, verified

Day 0's blockers have been executed. You are not starting from the audit in §1;
you are starting from a skeleton that lints, type-checks, respects the tier rule
and runs. Verified with the real toolchain, not asserted:

```
ruff check src tests     All checks passed!
ruff format --check      95 files already formatted
mypy src                 Success: no issues found in 93 source files
lint-imports             Analyzed 93 files, 56 dependencies. Contracts: 2 kept, 0 broken.
pytest -m "not docker"   no tests ran   (zero tests is passing)
yeet --version           yeet 0.1
yeet --help              lists all 10 commands
```

**What changed:**

| Change | Detail |
|---|---|
| `build-guide.md` → `yeet/docs/architecture.md` | the file every stub's docstring points at now exists |
| `Context.md` → `yeet/docs/getting-started.md` | — |
| root `README.md` rewritten | it was a byte-identical 47 KB copy of the build guide; now a ~30-line landing page pointing at `yeet/`, the two docs and this plan |
| `boostrap.py` → `yeet/tools/bootstrap.py` | typo fixed |
| `.DS_Store` × 3 untracked | added to `.gitignore` |
| **All ~60 stubs fixed** | missing imports added; §4 signatures applied; 43 mypy + 92 ruff errors → 0 |
| **`core/masking.py`** NEW | `Masker` — §3.1 |
| **`core/events.py`** NEW | `LogEvent`, `LogSink`, `FanOut`, `ListSink` — §3.2 |
| **`core/project.py`** NEW | `Project`, `Ecosystem` — §3.4 |
| **`core/graph.py`** NEW | `find_cycle`, `topo_waves` — §3.5, a fifth violation found while fixing the others |
| `secrets/masking.py` DELETED | superseded by `core/masking.py` |
| `actions/` moved to tier 2 | in `pyproject.toml` and in all four docstring headers |
| `pyproject.toml` mypy overrides | `docker`, `watchdog`, `ruamel`, `pathspec`, `keyring` ship no stubs — without this, `strict = true` fails the moment Dev C writes `import docker` |
| `cli/app.py` + all 10 `cmd_*.py` | every command registered with its real option surface; bodies call `todo()` |
| `cli/__init__.py` | exit-code constants: 0 ok, 1 job failed, 2 bad file, 3 no docker |
| `Makefile` | `make check` = the CI set |
| `docs/adr/0007` | records the tier decision and the verification output |
| `docs/architecture.md` banner | four of its placements are superseded by ADR 0007 — the banner says which, so nobody codes from the stale version |
| `docs/getting-started.md` | tier tree corrected (`actions/` is tier 2), bootstrap instructions replaced with a do-not-run warning |
| `tools/bootstrap.py` | warning header: its embedded stubs predate Day 0 and `--force` would revert it |
| CI + `Makefile` | CI now runs all five `make check` gates (`mypy` and `ruff format --check` were missing); `make rules` fails readably instead of with a traceback |
| `cli/__init__.py::todo()` | exits **1**, not 0 — a placeholder that reports success would defeat the validation gate |
| whole tree `ruff format`ted | pre-commit would have done this on the first commit anyway; better now than mid-PR on Tuesday |

**Two conventions this locked in.** Both are worth knowing before you write your
first command:

- **CLI options use `Annotated`**, not the classic style:
  `path: Annotated[Path, typer.Option("--path")] = Path()`. The classic form
  trips ruff's B008 on every parameter. A required argument has *no* default —
  `= ...` is classic-style and mypy rejects it.
- **`Status` and `Severity` stay `(str, Enum)`**, not `StrEnum`, with a
  `# noqa: UP042`. StrEnum changes what `str()` returns and three modules format
  those values. It is a one-line change whenever the team wants it.

Your first task is your own section in §5. §2 is kept below as a record.

---

## 1. Current state — an honest audit

`bootstrap.py` has run. What exists is a **skeleton, not a partial build.**

### 1.1 What is real code (do not rewrite, only extend)

| File | Lines | Status |
|---|---|---|
| `src/yeet/core/diagnostics.py` | 104 | ✅ Complete. `Severity`, `Position`, `Diagnostic`, `DiagnosticBag`. **Frozen contract #1.** |
| `src/yeet/core/ir.py` | 93 | ✅ Complete. `Step`, `Strategy`, `Job`, `Trigger`, `Workflow`. **Frozen contract #2.** |
| `src/yeet/core/result.py` | 65 | ✅ Complete. `Status`, `StepResult`, `JobResult`, `RunResult`. |
| `src/yeet/core/codes.py` | 68 | 🟡 Real, but only 18 of ~55 rules registered. Append-only from here. |
| `src/yeet/parser/aliases.yml` | 40 | 🟡 Real data, ~24 aliases. Append-only. |
| `src/yeet/analyzer/markers.py` | 14 | 🟡 3 of 13 ecosystems filled in. |
| `pyproject.toml` | 100 | ✅ Deps, ruff, mypy strict, pytest markers, **import-linter tier contract**. |
| `.github/workflows/ci.yml` | 27 | ✅ 3-OS × 2-Python matrix, runs ruff + lint-imports + pytest. |
| `.pre-commit-config.yaml`, `.gitattributes`, `.gitignore`, `.editorconfig` | — | ✅ Done. |

### 1.2 What is a stub

**Everything else.** All ~60 remaining `.py` files are 7–20 lines: a docstring
with `Owner:` / `Tier:`, `from __future__ import annotations`, and either a
signature raising `NotImplementedError` or nothing at all. The ten `cli/cmd_*.py`
files contain a docstring and **no code whatsoever** — not even a function.

Do not mistake a stub signature for a design that has been agreed. Several of
them are wrong or incomplete; §4 supersedes them.

### 1.3 What is missing entirely (nobody owns these yet — §2 assigns them)

| Missing | Why it matters |
|---|---|
| `docs/architecture.md` | **Every stub's docstring says "See docs/architecture.md".** It does not exist. The root `README.md` / `build-guide.md` *is* that document. |
| `docs/rules.md` | `yeet explain` reads it; `README.md` links it. |
| `src/yeet/parser/schema/workflow.schema.json` | Directory exists, empty. Layer 2 cannot start without it. |
| `src/yeet/templates/` content | `init --auto` and `hooks install` both render from here. Only an empty `hooks/` dir exists. |
| `Makefile` | `Context.md` §8 asks for it on Day 1. |
| `Dockerfile.base` | Guide §3.5: `ubuntu:22.04` has no git/node/curl. Workflows will fail mysteriously without this. |
| All tests | `tests/{unit,e2e,invalid,corpus,fixtures/valid}` contain only `.gitkeep`. `conftest.py` has one fixture. |
| ADRs 0002–0006 | Listed in `docs/adr/0001`, none written. These are the presentation's "why" slides. |

### 1.4 Repo-level defects — ✅ all four fixed, see §0

1. **`README.md` and `build-guide.md` at the repo root are byte-identical** (both
   47,341 bytes, md5 match). One of them must go — see §2.1.
2. **`boostrap.py` is misspelled** (`Context.md` line 6 tells people to run
   `bootstrap.py`, which doesn't exist).
3. **Stubs reference undefined names.** `analyzer/discover.py` annotates
   `root: Path` with no `from pathlib import Path`; `validation/layer0_file.py`
   returns `DiagnosticBag` with no import; `parser/builder.py`, `planner/graph.py`
   and others do the same. `from __future__ import annotations` means this does
   not crash at runtime — but `mypy src` (configured `strict = True`) fails on
   every one of them, so CI is red before a single feature lands.
4. **`src/yeet/.DS_Store` and `yeet/.DS_Store` are tracked.** Add `.DS_Store` to
   `.gitignore` and `git rm --cached` them.

---

## 2. Day 0 — blockers ✅ DONE

Kept as the record of what was done and why. §2.4 and §2.5 are the only items
still outstanding, and both need the four of you rather than a commit.

### 2.1 Documentation and repo hygiene — Dev D

```bash
git mv build-guide.md yeet/docs/architecture.md   # the file every stub points at
git rm README.md                                   # duplicate; yeet/README.md is the real one
git mv Context.md yeet/docs/getting-started.md
git mv boostrap.py yeet/tools/bootstrap.py         # fix the typo, park it
printf '.DS_Store\n' >> yeet/.gitignore
git rm --cached yeet/.DS_Store yeet/src/.DS_Store
```

Then add a `plan.md` link to `yeet/README.md` under Development.

**Done when:** `docs/architecture.md` exists, no duplicate 47 KB files, `git status` clean.

### 2.2 Make the skeleton type-check — Dev A (30 min, mechanical)

Walk every stub in `src/`. Add the imports the annotations need. Replace bare
`raise NotImplementedError` bodies in files whose signature §4 changes.

```bash
mypy src && ruff check src && lint-imports    # must all pass on the empty skeleton
```

**Done when:** all three commands exit 0 on `main` with zero features implemented.
This is the tripwire that keeps CI honest for the rest of the week.

### 2.3 Verify the tier contract actually bites ✅ done — result below

`pyproject.toml` groups tier 5 as `yeet.executor | yeet.actions | yeet.storage | yeet.secrets`.
In import-linter, `|`-separated siblings are **independent** — they may not import
each other. Confirm it empirically before §3 depends on it:

```bash
# temporarily add `from yeet.secrets import masking` to src/yeet/executor/script.py
lint-imports        # must FAIL. revert.
```

**Result — it fails, so §3 is mandatory, not optional:**

```
Layered architecture (a module may only import from lower tiers) BROKEN
yeet.executor is not allowed to import yeet.secrets:
- yeet.executor.script -> yeet.secrets.masking (l.12)
```

Recorded in `docs/adr/0007`. The probe import was reverted.

### 2.4 Read the frozen contracts out loud, then freeze — everyone ⬅ STILL TO DO

`core/ir.py` and `core/diagnostics.py`. Argue about field names now. After this
meeting, changing a field requires all four people in a standup, because Dev B's
planner, Dev C's executor and Dev D's renderer all destructure them.

### 2.5 Environment parity — everyone ⬅ STILL TO DO (one per machine)

```bash
python -m venv .venv && source .venv/bin/activate    # PS: .venv\Scripts\Activate.ps1
pip install -e ".[dev]" && pre-commit install
git config core.autocrlf input                        # skip this = the \r bug on Thursday
yeet --help && pytest -m "not docker"
```

Anyone whose env is broken at lunch is the week's critical path. Fix it today.

### 2.6 Write the Makefile ✅ done

```make
.PHONY: check test lint types imports fmt
check: lint imports types test
lint:    ; ruff check src tests
fmt:     ; ruff check src tests --fix && ruff format src tests
imports: ; lint-imports
types:   ; mypy src
test:    ; pytest -m "not docker" -q
docker:  ; pytest -m docker -q
```

---

## 3. Five architecture calls ✅ made and implemented

These are the decisions that, left unmade, surface as a `lint-imports` failure on
Wednesday afternoon when two people's branches are half-merged. §2.3 confirmed
empirically that the contract rejects the sibling imports, so all five are
mandatory. All five are on disk; `docs/adr/0007` is the write-up.

**The through-line: when the tier rule blocks an import, push the pure part
down into `core/` and leave the policy up top.** Every one of the five is that
same move, and each indirection turned out to be worth having on its own.

### 3.1 Masking cannot live in `secrets/` — move the pure function to `core/`

**Problem:** The executor must mask every stdout/stderr line before it reaches the
terminal (guide §5). `executor/` and `secrets/` are independent siblings at tier 5,
so `executor` importing `secrets.masking` is a contract violation.

**Decision:** split it.

- **New file `src/yeet/core/masking.py`** (tier 0, Dev D): `Masker` class —
  `add(value: str)`, `mask(line: str) -> str`. Pure string work, zero imports.
  On `add`, also register the base64 and URL-encoded variants of the value; that
  gap is what most homebrew runners miss and it is worth a slide.
- **`secrets/store.py`** (tier 5, Dev D) keeps only loading/decryption and returns
  `dict[str, str]`.
- **`cli/cmd_run.py`** (tier 7) is what wires them: load secrets → build a `Masker`
  → hand it to the backend.

`secrets/masking.py` becomes a two-line re-export of `core.masking` for
backwards-compatibility, or is deleted. Prefer deleted.

### 3.2 The executor must not import `storage/` — invert it with a sink Protocol

**Problem:** identical to §3.1. `executor` needs to write JSONL run logs, which
live in `storage/runs.py`.

**Decision:** **New file `src/yeet/core/events.py`** (tier 0, Dev C + Dev D):

```python
@dataclass(frozen=True, slots=True)
class LogEvent:
    ts: float; job: str; step: str; stream: str; text: str

class LogSink(Protocol):
    def emit(self, event: LogEvent) -> None: ...
```

The executor takes a `LogSink` and calls `emit()`. `storage/runs.py` implements
it writing JSONL; `reporting/console.py` implements it drawing the live tree.
`cli/cmd_run.py` constructs both and passes a fan-out sink. This also means Dev C
can test the executor with a list-appending fake and no filesystem.

### 3.3 `actions/` resolves, it does not execute

**Problem:** `actions/` and `executor/` are also independent siblings, yet
`actions/composite.py` conceptually "runs steps".

**Decision:** `actions/` is a **pure resolver**. Given a `uses:` string plus the
project root, it returns IR:

```python
def resolve(uses: str, root: Path, bag: DiagnosticBag) -> ResolvedAction | None
# ResolvedAction(kind="composite"|"docker"|"node", steps=[Step,...],
#                image=None, entrypoint=None, inputs={...}, action_dir=Path)
```

The executor consumes `ResolvedAction` and does all process/container work.
`executor` → imports `actions` is legal (tier 5 → tier 5 sibling is *not* — so
`actions/` must sit at **tier 2 alongside `parser/`**). Dev A: move the
`yeet.actions` entry in `pyproject.toml`'s layer list down to the
`yeet.parser | yeet.analyzer` line as part of §2.2, and re-run `lint-imports`.

### 3.4 `Project` and `Ecosystem` belong in `core/`, not `analyzer/`

**Problem:** `analyzer/project.py::analyze()` returns `Project`, which the
`scan` renderer wants to format. `reporting/` is tier 1, `analyzer/` is tier 2 —
the renderer cannot import it.

**Decision:** **New file `src/yeet/core/project.py`** (tier 0, Dev A):

```python
@dataclass(frozen=True, slots=True)
class Ecosystem:
    name: str; marker: Path; suggested_image: str; default_commands: list[str]

@dataclass
class Project:
    root: Path
    flows: list[Path] = field(default_factory=list)
    foreign_ci: list[Path] = field(default_factory=list)   # .gitlab-ci.yml etc.
    ecosystems: list[Ecosystem] = field(default_factory=list)
    is_git: bool = False
    branch: str | None = None
    dockerfile: Path | None = None
```

### 3.5 Layer 3 cannot import `planner.graph` either — the cycle walk moves to core

**Found while implementing §3.1–3.4, and not in the original audit.** The guide
says `planner/graph.py::find_cycle()` does double duty: the scheduler needs it
and Layer 3 calls the same function for E302, so write it once. But `validation`
is tier 3 and `planner` is tier 4 — that is an *upward* import, the exact thing
the contract exists to stop. Writing a second cycle detector inside L3 is worse:
two copies drift, and then the validator and the planner disagree about whether
a workflow is runnable.

**Decision: new `src/yeet/core/graph.py`** (tier 0, Dev B).

```python
Deps = Mapping[str, Sequence[str]]
def find_cycle(deps: Deps) -> list[str] | None    # returns the PATH: build -> test -> build
def topo_waves(deps: Deps) -> list[list[str]]
```

It takes a plain `{node: [deps]}` map and returns names — it knows nothing about
`Job` or `Workflow`, which keeps `core` free of IR semantics and makes it
trivial to test. `planner/graph.py` is now a ten-line Job-shaped adapter over
it, and `layer3_semantic.py` imports `find_cycle` directly. Written once, as
the guide intended, just at the bottom of the stack instead of the middle.

Unknown dependency names are treated as satisfied by `topo_waves`: a typo'd
`needs:` is E301's job to report, and it should not also produce a spurious
cycle error on top.

---

**These five files (`core/masking.py`, `core/events.py`, `core/project.py`,
`core/graph.py`, plus the `pyproject.toml` layer edit) are the only additions to
`core/` this week.** They are merged. `core/` is closed again — a sixth needs
the same all-four sign-off as `ir.py`.

---

## 4. The contract sheet

Code against these signatures. If your module needs something not on this list
from another person's module, ask them for the function — do not reach into their
files.

**These are now what is on disk**, docstrings included — the ⚠️ items from the
first draft have been applied, so the stub you open already has the right
signature. Changing one is a PR that touches everyone who calls it.

```python
# --- tier 0: core (frozen after Day 0) --------------------------------------
core.diagnostics : Severity, Position, Diagnostic, DiagnosticBag
core.ir          : Step, Strategy, Job, Trigger, Workflow
core.result      : Status, StepResult, JobResult, RunResult
core.codes       : Rule, RULES, get(code) -> Rule
core.project     : Project, Ecosystem                                    # §3.4 DONE
core.masking     : Masker — add/update/mask, +base64 +urlencoded         # §3.1 DONE (implemented)
core.events      : LogEvent, LogSink, FanOut, ListSink                   # §3.2 DONE (implemented)
core.graph       : find_cycle(deps) -> list[str] | None                  # §3.5 DONE
                   topo_waves(deps) -> list[list[str]]
core.config      : config_dir() -> Path; cache_dir() -> Path
                   load_lint_config(root: Path) -> dict[str, str]        # .yeet/lint.yml
cli (package)    : EXIT_OK=0  EXIT_JOB_FAILED=1  EXIT_BAD_WORKFLOW=2  EXIT_NO_DOCKER=3
                   todo(command, owner)   # placeholder; delete yours when you implement it

# --- tier 1 ------------------------------------------------------------------
reporting.render   : render_diagnostics(bag: DiagnosticBag, *, color: bool = True) -> str
reporting.json_out : to_json(bag) -> str
reporting.sarif    : to_sarif(bag) -> str
reporting.console  : RunConsole  implements core.events.LogSink
expressions.ast_nodes : Node, Literal, Ident, Member, Index, Splat, Unary, Binary, Call
                        ExprSyntaxError(offset, message)
expressions.parser    : parse(src: str) -> Node          # raises ExprSyntaxError(offset, msg)
expressions.evaluator : evaluate(node: Node, ctx: Contexts) -> object
expressions.contexts  : Contexts (dataclass: github, env, job, steps, runner,
                                  matrix, needs, secrets, inputs, vars) + Contexts.NAMES
                        build_github_context(root: Path, event: str) -> dict[str, object]
expressions.functions : hash_files(patterns, root) -> str  + the 10 builtins

# --- tier 2 ------------------------------------------------------------------
analyzer.root        : find_root(start: Path) -> Path
analyzer.discover    : discover_flows(root: Path) -> tuple[list[Path], list[Path]]  # (flows, foreign_ci)
analyzer.fingerprint : fingerprint(root: Path) -> list[Ecosystem]
analyzer.project     : analyze(start: Path) -> Project
parser.loader        : load_with_positions(path: Path, bag: DiagnosticBag) -> Any | None
parser.aliases       : normalize(node: Any) -> tuple[Any, bool]         # (tree, used_dialect)
parser.builder       : build_workflow(data, source: Path, bag) -> Workflow | None
actions.resolver     : resolve(uses, root, bag) -> ResolvedAction | None  # §3.3, tier 2 now

# --- tier 3 ------------------------------------------------------------------
validation.pipeline : validate_file(path, *, strict=False, upto=4) -> tuple[DiagnosticBag, Workflow | None]
validation.layer0_file     : check(path: Path) -> DiagnosticBag
validation.layer1_yaml     : check(path: Path) -> tuple[DiagnosticBag, Any | None]
validation.layer2_schema   : check(data: Any, path: Path) -> DiagnosticBag
validation.layer3_semantic : check(wf: Workflow) -> DiagnosticBag
validation.layer4_lint.base : LintRule Protocol, RULES, register(rule)
                              run_lints(wf, path, cfg) -> DiagnosticBag
validation.suggest         : did_you_mean(word: str, candidates: Iterable[str]) -> str | None

# --- tier 4 ------------------------------------------------------------------
planner.matrix : expand(job: Job) -> list[dict[str, object]]     # include then exclude
planner.graph  : to_deps(jobs) -> dict[str, list[str]]           # thin adapter over core.graph
                 topo_waves(jobs: dict[str, Job]) -> list[list[str]]
                 find_cycle(jobs: dict[str, Job]) -> list[str] | None
planner.plan   : JobInstance(job: Job, leg: dict, key: str)
                 ExecutionPlan(waves: list[list[JobInstance]])
                 build_plan(wf: Workflow, ctx: Contexts) -> ExecutionPlan

# --- tier 5 ------------------------------------------------------------------
executor.backend : Backend Protocol — run_job(inst: JobInstance, ctx: JobContext) -> JobResult
                   JobContext(workspace, env, secrets: Masker, sink: LogSink | None,
                              needs: dict[str, JobResult], event: str)
executor.paths   : to_container_path(host: Path) -> str
executor.platform_ : is_wsl() -> bool; is_windows() -> bool; docker_user() -> str | None
executor.script  : write_step_script(text: str, dest: Path) -> None   # LF bytes, always
executor.state_files : read_back(step_dir) -> dict[str, dict[str, str]]
executor.commands    : parse_workflow_command(line: str) -> Command | None   # ::group:: etc.
executor.images  : resolve_image(job: Job, project: Project) -> ImageSpec
executor.build   : build_tag(dockerfile: Path) -> str; ensure_built(spec) -> str
storage.runs     : RunStore implements LogSink; replay(run_id) -> Iterator[LogEvent]
secrets.store    : load_secrets(root: Path, overrides: dict) -> dict[str, str]

# --- tier 6/7 ----------------------------------------------------------------
triggers.watcher : watch(paths, on_change)          # 500 ms debounce, per-project lock
triggers.hooks   : install(root: Path, blocking: bool = False) -> list[Path]
cli.app          : app = typer.Typer(); one registration line per cmd_*.py
```

**The `(bag, workflow)` tuple from `validate_file` is the single most important
signature here.** It is what lets `cmd_run` validate and then plan without parsing
twice, and it is what makes `cmd_check`, `cmd_scan` and `cmd_graph` one-liners.

---

## 5. Who works on what

Four workstreams. Each table is **the definitive list of files that person edits
this week.** If you find yourself in someone else's directory, that is the signal
to ask them for a function.

Ordering within each table is dependency order — work top to bottom.

---

### Dev A — Frontend / DSL / Analyzer

You own the front half of the pipeline and the CLI shell. Everyone else's test
fixtures depend on you shipping discovery early, so §5.A.1 is the week's first
real deliverable.

| # | File | What to write | Done when |
|---|---|---|---|
| A1 | `src/yeet/core/project.py` | ✅ **DONE.** `Project`, `Ecosystem` per §3.4, plus `.stack` and `.has_flows` helpers for the scan header. | Merged. |
| A2 | *(all stubs)* | ✅ **DONE.** §2.2 — imports added, signatures applied. | `make check` green on the empty skeleton. |
| A2b | `src/yeet/cli/app.py`, all `cmd_*.py` | ✅ **DONE.** All 10 commands registered with their real option surface; bodies call `todo()`. **Delete the `todo()` call as you implement each one.** | `yeet --help` lists everything. |
| A3 | `src/yeet/analyzer/root.py` | Walk **up**: `.git/` → `.yeet/` → `.github/workflows/` → any manifest in `markers.py`. Stop at FS root or `$HOME`. Never shell out to git. | Unit tests for: git repo, bare dir, nested subdir, `$HOME` boundary. |
| A4 | `src/yeet/analyzer/markers.py` | Fill all 13 ecosystems from architecture.md §3.9 step 3 (currently 3). | Table complete, no `# ...` comment left. |
| A5 | `src/yeet/analyzer/discover.py` | Walk **down**. `EXCLUDE_DIRS` + `MAX_DEPTH=5` + `MAX_FILES=20_000` + `follow_symlinks=False` + inode visited-set + per-directory `PermissionError` handler. Return `(flows, foreign_ci)` — precedence `.yeet/flows/` > `.github/workflows/` > root `yeet.yml`. Detect-and-report `.gitlab-ci.yml`/`azure-pipelines.yml`/`Jenkinsfile`. Honor `.gitignore` via `pathspec`. | Tests build fixture trees under `tmp_path`: monorepo with `node_modules`, symlink loop, unreadable dir. Never hangs, never raises. |
| A6 | `src/yeet/analyzer/fingerprint.py` | Marker → `Ecosystem`. Read `engines.node` from `package.json` and `requires-python` from `pyproject.toml` to pin the tag instead of guessing. Polyglot = return all. | Correctly fingerprints this repo (Python) and a Node repo. |
| A7 | `src/yeet/analyzer/project.py` | `analyze()` = A3 → A5 → A6 + `is_git`, `branch`, `dockerfile`. No YAML parsed here. | Returns a populated `Project` for 3 real repos. |
| A8 | `src/yeet/cli/app.py` | ✅ scaffolded (A2b). What remains: a global `--no-color` that honors `NO_COLOR`. | `--no-color` suppresses color everywhere. |
| A9 | `src/yeet/cli/cmd_scan.py` | The §3.9 report block: project line, stack, markers, flows found with per-flow validity from `validate_file(..., upto=2)`, Dockerfile hint. Zero flows → suggest `yeet init --auto`, exit 0. | **Day 1 ship target: `yeet scan` on three real repos you didn't write.** |
| A10 | `src/yeet/parser/loader.py` | `ruamel.yaml` `typ="rt"`. Emit E101 from `problem_mark`, E102 duplicate keys (subclass the constructor to *raise* — PyYAML silently keeps the last), E103 non-mapping root, E104 multi-doc, W105 the `on:`→`True` trap (normalize the key, warn). | `tests/invalid/E101.yml`…`W105.yml` each emit exactly their own code. |
| A11 | `src/yeet/parser/aliases.py` | Load `aliases.yml` once, recursive key rewrite. Return `(tree, used_dialect)`. Never fails, never warns. `manual` → `workflow_dispatch` is an *event value*, not a key — handle in builder, not here. | Round-trip test: a canonical GH Actions file passes through unchanged. |
| A12 | `src/yeet/parser/schema/workflow.schema.json` | **NEW.** JSON Schema for the **canonical** form only (aliases already normalized away). | `jsonschema` validates the fixtures in `tests/fixtures/valid/`. |
| A13 | `src/yeet/validation/layer2_schema.py` | `jsonschema` + `best_match(validator.iter_errors(doc))`. Convert `error.absolute_path` deque → `jobs.build.steps[2].run`. E201 unknown key (with A15 suggestion), E202–E208. | Each of E201–E208 has an invalid fixture that fires only it. |
| A14 | `src/yeet/validation/layer1_yaml.py` | Thin wrapper over A10 for the pipeline's layer interface. | — |
| A15 | `src/yeet/validation/suggest.py` | `difflib.get_close_matches` against canonical keys **and** aliases. | `bild` → `build`; `the_grnd` → `the_grind`. |
| A16 | `src/yeet/parser/builder.py` | dict tree → IR. **Every `Step(...)` gets `pos=` from `data.lc.value(key)` as you build it** — not afterwards. Emit E204/E205. Populate `key_pos` for the fields lint will point at. Accept scalar `needs: build` and normalize to a list. | Golden-file tests: `tests/fixtures/<n>.yml` + `<n>.expected.json`, ~20 of them. |
| A17 | `src/yeet/actions/resolver.py` + `composite.py` | §3.3 pure resolver. Tier 1 = local composite (`./.yeet/actions/foo/action.yml`, `runs.using: composite`). `with:` → `INPUT_FOO`. Defaults from `action.yml`. Missing required input = hard error before the step runs. E313/E314/W319. | A composite action expands to `list[Step]` in a golden test. |
| A18 | `src/yeet/templates/` + `cli/cmd_init.py` | Jinja2 templates per ecosystem. `--auto` reads the fingerprint and writes a working `.yeet/flows/main.yml`. Also writes `.gitignore` entries for `.yeet/tmp/`, `.yeet/runs/`, `.yeet/.secrets`. | `yeet init --auto` in an empty Node dir → `yeet check` on the result is clean. |
| A19 | `./.yeet/actions/checkout/` (in the demo repo) | Ship your own checkout composite so the demo has zero external deps. | Demo workflow runs offline. |
| A20 | *stretch* `src/yeet/actions/` remote | `owner/repo@ref` → `git clone --depth 1` into `~/.yeet/actions/`, cached by ref. **Cut this first if Day 4 slips.** | — |

---

### Dev B — Expressions, Planner, Semantic validation 

You own the two subsystems that make the tool look clever, plus L3 — which is
deliberately yours because L3 *is* the same graph walk as the planner. Write the
walk once.

**The trap for you specifically** (architecture.md §11): the expression engine is
the most fun thing in this repo and it is very easy to spend three days building a
beautiful Pratt parser that nothing calls. A crude engine wired into the pipeline
on Day 2 beats a perfect one wired in on Day 5. **Never `eval()`.**

| # | File | What to write | Done when |
|---|---|---|---|
| B1 | §2.3 | ✅ **DONE.** Verified: the contract rejects sibling imports. Output in `docs/adr/0007`. | — |
| B1b | `src/yeet/core/graph.py` | ✅ **DONE** (signatures). §3.5 — the cycle walk moved to tier 0 so L3 can share it. **You implement the two functions**; `planner/graph.py` is already the adapter. | `find_cycle` returns the path; `topo_waves` groups correctly. |
| B2 | `src/yeet/expressions/lexer.py` | Tokenizer: literals (string/number/bool/null), identifiers, `. [ ] ( ) , * ! && \|\| == != < > <= >=`. Track byte offsets — E309 must report the offset *inside* the expression. | Table test of ~40 token streams. |
| B3 | `src/yeet/expressions/ast_nodes.py` | ✅ **DONE.** All 9 node types + `ExprSyntaxError(offset, message)`. Extend if your parser needs more. | — |
| B4 | `src/yeet/expressions/parser.py` | Hand-rolled Pratt parser, ~250 lines. Raise `ExprSyntaxError(offset, msg)`. | Precedence table test; every malformed input raises rather than returning garbage. |
| B5 | `src/yeet/expressions/contexts.py` | `Contexts` dataclass with all 11 contexts. `build_github_context(root, event)` fills `sha`, `ref`, `ref_name`, `repository`, `actor`, `event_name`, `workspace`, `run_id`, `run_number`. | `${{ github.ref_name }}` resolves in a real git repo. |
| B6 | `src/yeet/expressions/evaluator.py` | Walk the AST. **Replicate GitHub's loose equality** (`'1' == 1` true, `'' == 0` true) or document that you don't — silently differing is the one unacceptable option. Member access on a missing key returns `None`, not an error. | The CSV table test in §7 passes. |
| B7 | `src/yeet/expressions/functions.py` | `contains`, `startsWith`, `endsWith`, `format`, `join`, `toJSON`, `fromJSON`, `hashFiles`, `success`, `failure`, `always`, `cancelled`. **`hashFiles` must sort paths before hashing** or it returns different values per OS. | Cross-platform test asserts a fixed hash for a fixed tree. |
| B8 | `src/yeet/core/graph.py` (impl) | The algorithms themselves — see B1b. `planner/graph.py` needs no further work. | Cycle test, diamond-dependency test, single-job test. |
| B9 | `src/yeet/validation/layer3_semantic.py` | E301 (needs→unknown job, with a did-you-mean via A15), E302 (**imports `core.graph.find_cycle` — already wired, do not write a second detector**), E303–E308, E309–E311 (expression parse/context/function errors), E312, E316, E317 (warning; error under `--strict`), W318. | One invalid fixture per code, each firing exactly its own. |
| B10 | `src/yeet/planner/matrix.py` | Cartesian product of `matrix`, then apply `include` (adds legs / extends existing), **then** `exclude`. Order matters. `max-parallel` respected downstream. | `include`-extends-existing-leg test; `exclude`-after-include test. |
| B11 | `src/yeet/planner/plan.py` | `build_plan()`: matrix expansion → DAG → topo sort into `ExecutionPlan(waves)`. Evaluate job-level `if:` here. | Multi-job matrix workflow produces the expected wave structure. |
| B12 | `src/yeet/cli/cmd_graph.py` | ASCII DAG render. 30 lines. | `yeet graph` on the demo workflow looks good on a projector. |
| B13 | skip semantics | A job whose `needs` failed is **skipped** unless its `if:` uses `always()`/`failure()`. `fail-fast: true` cancels sibling matrix legs. Lives in `plan.py` + consumed by Dev C's runner loop. | Integration test with a deliberately failing upstream job. |

---

### Dev C — The executor (Docker, cross-platform)

You own the highest-risk subsystem. The whole week's schedule is built around
"does a container run a step by Wednesday" — if it slips past Wednesday, we cut
matrix and remote `uses:` immediately, so **shout early rather than grinding.**

You also own all cross-platform handling, deliberately confined to two files
(`paths.py`, `platform_.py`) so nobody else's module fills up with
`if sys.platform ==`.

| # | File | What to write | Done when |
|---|---|---|---|
| C1 | `src/yeet/core/events.py` | ✅ **DONE and implemented.** `LogEvent`, `LogSink`, `FanOut` (one event → several sinks, a failing sink counts rather than raises), `ListSink` (your test double — the executor needs no disk to test). | Merged. |
| C1b | `src/yeet/executor/backend.py` | ✅ **DONE.** `JobContext` + `Backend` Protocol per §4. | Merged. |
| C2 | `src/yeet/executor/platform_.py` | `is_wsl()` (read `/proc/version` for `microsoft`), `is_windows()`, `docker_user()` → `"uid:gid"` on Linux/WSL and **`None` on macOS/Windows** (passing a UID to Docker Desktop breaks things). | Unit tests with a mocked `platform`/`/proc/version`. |
| C3 | `src/yeet/executor/paths.py` | `to_container_path()`: `C:\Users\x\proj` → `/c/Users/x/proj`. Warn loudly if the repo is under `/mnt/c/` on WSL (10–20× slower I/O, broken file watching). | Unit-tested on all three OSes in CI — this is the one function the 3-OS matrix really earns its keep on. |
| C4 | `Dockerfile.base` | **NEW**, repo root. `ubuntu:22.04` + git, curl, ca-certificates, jq, unzip, build-essential, python3, node 20. Tag `yeet/ubuntu:22.04`. | Built locally by everyone; without it, workflows fail in confusing ways. |
| C5 | `src/yeet/executor/backend.py` | `Backend` Protocol + `JobContext` per §4. Docker daemon discovery with **platform-specific failure messages** ("Is Docker Desktop running?" / `sudo systemctl start docker` / "Enable WSL integration"). Exit code 3. | `yeet run` with the daemon stopped prints something a human can act on. |
| C6 | `src/yeet/executor/script.py` | `write_step_script()` — **always `write_bytes(text.replace("\r\n","\n").encode())`.** CRLF here is bug #1 on the "will bite you" list (`$'\r': command not found`). | Test asserts no `\r` in the output bytes, on Windows too. |
| C7 | `src/yeet/executor/workspace.py` | `.yeet/tmp/` layout, per-step script paths, per-run dirs, cleanup. | — |
| C8 | `src/yeet/executor/docker_backend.py` | **The core insight: one container per job, `exec_run` per step.** `containers.create(image, command=KEEPALIVE_CMD, working_dir="/workspace", volumes={host: {"bind": "/workspace", "mode": "rw"}}, user=docker_user())` → start → loop steps → `stop()`/`remove()` **in a `finally`**. Register `atexit` + SIGINT/SIGTERM handlers so Ctrl-C never leaves containers behind. Stream `demux=True` through `Masker.mask()` before it reaches the sink. | **Day 2 ship target (b): a single-job, three-step workflow runs in Docker.** |
| C9 | `src/yeet/executor/state_files.py` | `GITHUB_ENV` / `GITHUB_OUTPUT` / `GITHUB_PATH` / `GITHUB_STEP_SUMMARY` / `GITHUB_STATE` written per step, read back after each step, fed into the next step's env. Alias each as `YEET_*` too. Support the heredoc form for multiline values. | Step 1 writes `FOO=bar` to `$GITHUB_ENV`, step 2 echoes it. |
| C10 | `src/yeet/executor/commands.py` | Parse `::` directives from stdout: `group`/`endgroup`, `error`, `warning`, `notice`, `add-mask`, `debug`. `add-mask` updates the `Masker` **immediately**. | Each directive round-trips into a `LogEvent`/`Diagnostic`. |
| C11 | `src/yeet/executor/images.py` | Resolution table: `ubuntu-latest` → `yeet/ubuntu:22.04`; `image:tag` → pull; `./Dockerfile` → build; `local`/`native` → host shell. **No `cooked_on` + a root `Dockerfile` → build it**, and print `no cooked_on set → found ./Dockerfile → building`. E315 when nothing resolves. | All four rows exercised. |
| C12 | `src/yeet/executor/build.py` | `build_tag()` = `sha256(dockerfile + context file list)[:12]`; skip the build if the tag exists. That's the whole build cache, ~15 lines. | Second run of the same Dockerfile does not rebuild. |
| C13 | `src/yeet/executor/local_backend.py` | `cooked_on: local` — bash on Linux/macOS/WSL, `pwsh` (fallback `powershell`) on Windows. Honors `shell:`. | Runs the walking-skeleton workflow with no Docker at all. |
| C14 | `src/yeet/cli/cmd_run.py` | Wire it: analyze → validate (layers 0–3, **hard stop on any error, exit 2, before any container is created**; layer 4 prints but never blocks) → plan → run waves with a bounded pool (`--jobs N`, default `cpu_count`) → propagate `JobResult`s into the `needs` context → report. `--event`, `--job`, `--path`, `--secret K=V`, `-v`. | The full pipeline, end to end. |
| C15 | `src/yeet/actions/docker_action.py` consumption | Execute a `ResolvedAction(kind="docker")` from Dev A's resolver. | Day 4. |
| C16 | `src/yeet/actions/js_action.py` consumption | `runs.using: node20`, `main: dist/index.js`. **Cut if Day 5 is tight.** | — |
| C17 | `yeet prune` | Clear the build cache. Zombie `docker build` growth is real. | — |

---

### Dev D — Diagnostics, reporting, lint, secrets, triggers, tests

You own everything the user actually *sees*, plus the lint layer that turns "it
runs" into "it enforces conventions" — which is what the brief actually asked for.

**Your first two deliverables look like low-priority polish and are not.** The
renderer means every bug the other three hit for the rest of the week prints
legibly instead of as a stack trace. Write it Day 1.

| # | File | What to write | Done when |
|---|---|---|---|
| D1 | §2.1, §2.6 | ✅ **DONE.** Docs move, `Makefile`, `.gitignore`, ADR 0007. | — |
| D2 | `src/yeet/core/masking.py` | ✅ **DONE and implemented.** `Masker` with raw + base64 (padded and stripped) + urlsafe-base64 + URL-encoded variants, longest-first replacement, and a 4-char floor so short values don't redact the whole log. **Write the unit tests.** | A planted token and its base64 form are both `***`. |
| D3 | `src/yeet/core/events.py` | ✅ **DONE**, with Dev C. | — |
| D4 | `src/yeet/reporting/theme.py` | Symbols + colors. Status vocabulary: `slayed` / `flopped` / `mid` / `skipped (not the vibe)` / `cooked`. Disable color when `NO_COLOR` is set or stdout isn't a TTY. | — |
| D5 | `src/yeet/reporting/render.py` | **The code-frame renderer**, rustc/eslint style — the exact output block in architecture.md §3.10. 2 lines of context above, 1 below, right-aligned gutter. **Clamp every index to the line length and wrap the whole thing in `try/except` falling back to `str(diagnostic)`.** Your error reporter must never be the thing that errors. | Renders a 3-diagnostic bag correctly; a `Position(line=99999, col=-4)` still prints something. **Day 1 ship.** |
| D6 | `src/yeet/reporting/console.py` | `RunConsole` implementing `LogSink` — the live `rich` tree from architecture.md §5, with `::group::` sections collapsible. | Looks like the block in the guide. |
| D7 | `src/yeet/reporting/json_out.py` / `sarif.py` | `--format json` dumps the `Diagnostic` list; `--format sarif` emits SARIF 2.1.0. | VS Code's SARIF Viewer renders our findings inline. That's a 20-second demo beat. |
| D8 | `src/yeet/validation/pipeline.py` | Layers 0→4 in order. **Stop *between* layers, never *within* one** — a user who fixes one error per run will hate the tool. Return `(bag, workflow)`. Apply `.yeet/lint.yml` severity overrides. | `yeet check` on a file with 3 bad `needs:` reports all 3. |
| D9 | `src/yeet/validation/layer0_file.py` | E001 unreadable, E002 empty, E003 not UTF-8 (with byte offset), W004 BOM, **E005 tabs for indentation** (catch it with a regex yourself — YAML's native message is unreadable and this is extremely common), W006 CRLF, W007 >1 MB. | 7 invalid fixtures. |
| D10 | `src/yeet/core/config.py` | `config_dir()`/`cache_dir()` via `platformdirs`. `load_lint_config()` reads `.yeet/lint.yml` (`W403: error`, `W407: off`). Keep the Windows cache path shallow (`%LOCALAPPDATA%\yeet\`) — 260-char limit. | Correct paths on all three OSes. |
| D11 | `src/yeet/validation/layer4_lint/base.py` | ✅ Protocol + `register()` + `RULES` scaffolded. Implement `run_lints()` and apply D10's severity overrides. | Rules self-register; adding one is a file, not a wiring change. |
| D12 | `layer4_lint/naming.py` | W401 no name, W413 zero steps, W414 duplicated step blocks across jobs, I415 mixed dialect/canonical keys. | — |
| D13 | `layer4_lint/pinning.py` | W402 moving ref (`@main`/`@master`), W403 `:latest`, W411 deprecated `::set-output`/`::save-state`/`::set-env`, W412 EOL action versions. | — |
| D14 | `layer4_lint/secrets_scan.py` | **The highest-value rule in the repo.** `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`, `-----BEGIN .* PRIVATE KEY-----`, plus Shannon entropy > 4.0 bits/char on 20+ char literals. | W404 fires on a planted token, and does **not** fire on `${{ secrets.X }}`. |
| D15 | `layer4_lint/shell.py` | W405 multi-line `run:` without `set -euo pipefail`, W406 `run:` > 50 lines, W408 `continue-on-error` on a deploy-looking job. | — |
| D16 | `layer4_lint/portability.py` | W409 absolute host paths (`/home/`, `/Users/`, `C:\`), W410 path case mismatch vs. disk. | W410 catches `./Src/index.js` where the file is `src/index.js`. |
| D17 | `src/yeet/core/codes.py` | Append the ~37 missing rules. **Append at the end of your layer's block — appends merge cleanly, reordering does not.** | Every implemented rule has a row. |
| D18 | `docs/rules.md` + `tools/gen_rules_doc.py` | **Generate** the index from `codes.py` so it cannot drift. One section per code: meaning, triggering example, fix, how to disable. | `docs/rules.md` regenerates identically in CI. |
| D19 | `src/yeet/cli/cmd_check.py` | `--strict`, `--format json\|sarif`, exit 0/2. All 5 layers. | **Day 2 ship (a): a broken YAML file produces a real code frame.** |
| D20 | `src/yeet/cli/cmd_explain.py` | `yeet explain YEET-E301` prints that section of `docs/rules.md`. | — |
| D21 | `src/yeet/secrets/store.py` | Precedence: `--secret K=V` → `.yeet/.secrets` (Fernet, key derived by scrypt from a passphrase) → OS keyring → `.env`. Never write secrets into a workflow file. | `yeet secrets set NPM_TOKEN` round-trips. |
| D22 | `src/yeet/cli/cmd_secrets.py` | `set` / `list` (names only, never values) / `rm`. | — |
| D23 | `src/yeet/storage/runs.py` | `RunStore` implements `LogSink` → JSONL at `.yeet/runs/<run-id>/`, one object per line: `{ts, job, step, stream, text}`. `replay()` reads it back. | — |
| D24 | `src/yeet/cli/cmd_logs.py` | `yeet logs [run-id]` replays the JSONL through D6's console. **This is why the log format stays tested — every use of the command exercises it.** | — |
| D25 | `src/yeet/storage/artifacts.py` / `cache.py` | `loot:` → copy to `.yeet/artifacts/<run-id>/<name>/`. `stash:` → tarball at `~/.cache/yeet/cache/<sha256(key)>.tar.zst`, with `restore-keys` prefix matching. | — |
| D26 | `src/yeet/triggers/watcher.py` + `cli/cmd_watch.py` | `watchdog` observer, **500 ms debounce** (without it: a run writes files → triggers a run → …), per-project lock, ignore `.git`/`node_modules`/`target`/`.yeet/tmp`. A broken file logs and waits — it must never crash the daemon. | Runs for 10 minutes over an active edit session without a runaway loop. |
| D27 | `src/yeet/triggers/hooks.py` + `cli/cmd_hooks.py` + `templates/hooks/` | Write `post-commit` and `pre-push` shims calling `yeet run --event push --sha $(git rev-parse HEAD)`. `chmod 0o755`. Shebang-`sh` so Git for Windows works. Non-blocking by default; `--blocking` fails the push on red. `pre-push` runs `yeet check --strict`. | `git commit` fires a run. |
| D28 | `tests/` (all of it) | See §7. You own the harness; each person writes the fixtures for their own rules. | §7 targets met. |
| D29 | ADRs 0002–0006 | 20 min each, split across the team, but you chase them. | Five files in `docs/adr/`. |

---

## 6. Schedule

Ship targets are what gets demoed at the daily 15-minute sync. Anyone blocked
more than two hours escalates rather than waiting for the sync.

| Day | Dev A | Dev B | Dev C | Dev D | **Ship** |
|---|---|---|---|---|---|
| **0** | ✅ A1, A2, A2b | ✅ B1, B1b | ✅ C1, C1b | ✅ D1, D2, D3 | ✅ done — `make check` green, `yeet --help` works. Outstanding: freeze the IR out loud (§2.4) and one env per machine (§2.5). |
| **1** | A3–A7 | B2–B4 | C2–C4, C5 | D4, D5 | **`yeet scan` finds flows in 3 real repos** · code frames render |
| **2** | A8–A9, A10–A11 | B5–B7 | C6–C8 | D8–D10, D19 | **(a) `yeet check` shows a real code frame · (b) 3 steps run in one container** ← the two that de-risk the week |
| **3** | A12–A16 | B8–B10, B13 | C9–C11 | D11–D16 | multi-job DAG + matrix · top 10 lint rules fire |
| **4** | A17–A19 | B11–B12 | C12–C15 | D17, D18, D20, D23–D25 | **end-to-end on a Node repo and a Python repo neither of us wrote** |
| **5** | A20 *(cut first)* | polish | C16 *(cut second)*, C17 | D21–D22, D26–D27 | triggers work · **cross-platform day: one person per OS, fix every path/CRLF/permission bug** · features freeze |
| **6** | — | — | — | D28, D29 | hardening, packaging (`pipx install .`), **two full dry runs of the demo** |
| **7** | Demo. Have a recorded video fallback — Docker on a projector laptop is not to be trusted. |

**Walking skeleton (Day 1, wire it now, let it stay red for two days):**

```yaml
vibe: hello
when: {push: {}}
the_grind:
  build:
    cooked_on: ubuntu-latest
    moves:
      - bet: echo "we are so back"
```

`tests/e2e/test_walking_skeleton.py` asserts `yeet run` exits 0 and prints that
string. Dev D writes it Day 1. It will fail until Day 2 — that is the point. It is
the tripwire that tells us instantly who broke the seam between two subsystems,
and it is the specific thing that stops us from discovering on Thursday that four
perfectly-built subsystems don't connect.

**Cut list, in the order we cut** if Day 2 ship (b) slips: A20 remote `uses:` →
C16 JS actions → D25 cache → C15 Docker actions. Say so out loud at the sync;
silent scope reduction is how two people end up building the same fallback.

---

## 7. Testing obligations

Owned by Dev D as harness; **each person writes the fixtures for their own rules.**

| Kind | Location | Target | Owner |
|---|---|---|---|
| Golden parser files | `tests/fixtures/valid/<n>.yml` + `<n>.expected.json` | ~20 | A |
| **Invalid corpus** | `tests/invalid/<CODE>.yml` — one file per code, broken in exactly one way, named for the code it must emit. One parametrized test asserts `codes_emitted(f) == {f.stem}`. | one per implemented rule (~40) | rule's author |
| Expression table | `tests/unit/expressions.csv` — `expr, context, expected` | ~60 rows | B |
| Discovery trees | `tests/unit/test_discover.py` — git repo, bare folder, monorepo with `node_modules`, symlink loop, unreadable dir | 6 | A |
| Executor | `@pytest.mark.docker`, skipped when the daemon is absent | — | C |
| E2E | `tests/e2e/test_walking_skeleton.py` | 1, then more | D |
| **Compatibility corpus** | `curl` 5–10 real `.github/workflows/*.yml` from popular OSS into `tests/corpus/`, run `yeet check` on all of them, report **"% of syntax supported"** + every unsupported key hit | 10 files | D |

The invalid corpus is ~40 tests for an hour of work, it proves every rule fires,
it catches the classic bug where fixing one rule silently breaks another, and it
is the single best artifact to put in front of a trainer. Do it properly.

The compatibility-corpus percentage is a concrete metric for the presentation,
and its unsupported-key list writes the non-goals slide for us.

---

## 8. Merge protocol

**Exactly five files more than one person touches.** Treat them carefully:

| File | Rule |
|---|---|
| `src/yeet/cli/app.py` | All 10 registrations already exist. You will rarely touch it — you edit your own `cmd_*.py` instead. If you add a command, append one line to the marked block. **Do not reformat the file.** |
| `src/yeet/core/codes.py` | Append rows at the end of *your layer's* block. Appends merge; reordering doesn't. |
| `src/yeet/parser/aliases.yml` | Append only. |
| `pyproject.toml` deps | Announce in chat before adding one. |
| `core/ir.py`, `core/diagnostics.py` | Frozen after Day 0. A change needs all four people in a standup. |
| the rest of `core/` | `masking`, `events`, `project`, `graph`, `codes`, `result`, `config` — everything imports these. Adding a function is fine; changing an existing signature is a standup item. |

Everything else has exactly one owner (see §5, and the `Owner:` line in every
stub's docstring). **If you're editing someone else's directory, stop and ask them
for a function instead.**

- `main` is protected, PRs only, CI must be green.
- Branches: `feat/<area>/<thing>`, e.g. `feat/analyzer/root-detection`. Area-first
  means `git branch -a` doubles as a status board.
- **`git pull --rebase origin main` before every push.** Four people merging
  `main` into their branches produces a commit graph nobody can read by Wednesday.
- **Merge to `main` daily, even when incomplete.** A stub that raises
  `NotImplementedError` merged Tuesday beats a perfect module merged Friday,
  because the former lets three other people import it and keep moving.
- Open one issue per stub file, assigned to the owner in its docstring header.

---

## 9. Risk register

| # | Risk | Mitigation | Owner |
|---|---|---|---|
| 1 | Docker execution slips past Wednesday | Hard checkpoint at Day 2 ship (b). If it slips, cut §6's list immediately and lead the demo with validation, which needs no daemon. | C, escalate to all |
| 2 | `print()` for an error creeps in | Everything user-facing is a `Diagnostic`. **Add a CI grep for `print(` under `src/`.** It'll be a hurried `print(f"bad key: {k}")` in the parser and it will still be there on Friday. | D |
| 3 | Expression engine gets gold-plated before it's wired | Walking skeleton Day 1; B ships a crude `evaluate()` on Day 2 and improves it after. Hold each other to it. | B |
| 4 | Positions retrofitted onto the IR | `pos=` is set **as** each node is constructed in `builder.py`. Retrofitting is a parser rewrite. Reject any PR that adds a node without one. | A |
| 5 | CRLF in step scripts (`$'\r': command not found`) | `write_step_script` writes LF bytes unconditionally; `.gitattributes`; `git config core.autocrlf input` on every machine Day 0. | C |
| 6 | Root-owned files in the workspace after a run | `user=uid:gid` on Linux/WSL only — **never** on Docker Desktop. | C |
| 7 | Watcher trigger loop (a run writes files → triggers a run) | 500 ms debounce + per-project lock + ignore `.yeet/`. | D |
| 8 | The renderer crashes on a bad position | Clamp every index; wrap in `try/except`; fall back to `str(diagnostic)`. Test it with a deliberately absurd `Position`. | D |
| 9 | Containers survive Ctrl-C | `finally` + `atexit` + SIGINT/SIGTERM handlers. | C |
| 10 | `lint-imports` fails mid-merge on a tier violation | §3 resolves the four known ones on Day 0. Run `make check` before every push. | all |
| 11 | Secrets leak into logs through a stream someone forgot to filter | Masking is applied at the single point where the executor emits a `LogEvent` — one chokepoint, not per call site. | C + D |
| 12 | `hashFiles()` differs across OSes | Sort paths before hashing; the 3-OS CI matrix asserts a fixed hash. | B |

---

## 10. Definition of done for the week

The demo runs **analyse → validate → run**, in that order — that's the story the
brief describes, and validation demos survive a projector far better than Docker.

- [ ] `yeet scan` on a freshly-cloned OSS repo identifies the stack and finds its workflows
- [ ] `yeet check` produces a full code-frame report: unknown key with a did-you-mean, a `needs:` pointing at a nonexistent job, a hardcoded token flagged
- [ ] `yeet run` on that broken file **refuses**, non-zero exit — the gate is visible
- [ ] `yeet init --auto` generates a working flow for a detected stack
- [ ] The **same workflow in standard GitHub Actions syntax also runs** — superset, not replacement
- [ ] `yeet graph` renders the DAG
- [ ] `yeet run` shows live matrix, parallel jobs, grouped colored logs
- [ ] A deliberately failing test → `flopped`, downstream job skipped, non-zero exit
- [ ] A repo with only a `Dockerfile` → auto-detect, build, cache, run
- [ ] `yeet hooks install` → `git commit` fires a run
- [ ] Green 3-OS CI badge + the "% of real-world syntax supported" number
- [ ] Non-goals stated out loud (architecture.md §9): no Windows containers, no runner registration, no reusable workflows, no OIDC, no full toolkit API
