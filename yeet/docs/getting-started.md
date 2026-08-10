# Getting Started — Day 0 to first green run

Companion to [`architecture.md`](architecture.md). That one says *what* to build;
this one says *where each thing lives* and *what to do in which order*.

> **The skeleton already exists — do not run `tools/bootstrap.py`.**
> It generated this tree once, and it has since fallen out of date: its embedded
> stubs still carry the pre-Day-0 signatures and it still writes
> `secrets/masking.py`, which we deleted. Running it with `--force` would revert
> Day 0. Clone the repo instead.

```bash
git clone <this repo> && cd yeet
python -m venv .venv && source .venv/bin/activate   # PS: .venv\Scripts\Activate.ps1
pip install -e ".[dev]" && pre-commit install
make check                                          # must be green before you start
```

Day 0's mechanical work is done: the skeleton lints, type-checks, satisfies the
tier contract and `yeet --help` runs. See [`../../plan.md`](../../plan.md) §0 for
exactly what changed and [`adr/0007`](adr/0007-tier-rule-consequences.md) for the
architectural consequences that this document's §1 tree predates.

---

## 1. Why the directory tree looks like this

There is exactly one organising principle: **directories are owned, and
imports only ever point downhill.**

Four people editing one repo for a week fail in one of two ways — merge
conflicts, or someone's half-finished module breaking everyone else's imports.
The layout kills both. Each person owns whole directories, so you rarely touch
the same file. And the tier rule means a broken module can only break things
*above* it, never below.

```
src/yeet/
├── core/          tier 0   ← FROZEN. Imports nothing. Everyone imports it.
│                             ir · diagnostics · result · codes · config
│                             masking · events · project · graph   ← see ADR 0007
├── expressions/   tier 1   Dev B
├── reporting/     tier 1   Dev D
├── parser/        tier 2   Dev A
├── analyzer/      tier 2   Dev A
├── actions/       tier 2   Dev A + C   ← resolves `uses:` to IR, executes nothing
├── validation/    tier 3   Dev A (L1,L2) · B (L3) · D (L0,L4)
├── planner/       tier 4   Dev B
├── executor/      tier 5   Dev C
├── secrets/       tier 5   Dev D
├── storage/       tier 5   Dev D
├── triggers/      tier 6   Dev D
└── cli/           tier 7   everyone owns their own cmd_*.py
```

**The rule: a module may import from lower tiers only. Never sideways, never
up.** `executor` never imports `cli`. `parser` never imports `executor`. If two
modules at the same tier need to share something, it moves down into `core`.

That last sentence is not hypothetical — it happened four times on Day 0. The
executor cannot import `secrets` or `storage` (independent siblings), and
validation cannot import `planner` (that's upward), so masking, the log sink and
the cycle walk all moved down into `core/`, and `actions/` moved from tier 5 to
tier 2. [`adr/0007`](adr/0007-tier-rule-consequences.md) has the verification
output and the reasoning.

This isn't a suggestion you have to police in review — `pyproject.toml` ships
an `import-linter` contract that enforces it. `lint-imports` fails CI the
moment someone violates it. That one command replaces about six arguments
you'd otherwise have on Thursday.

### The two frozen contracts

`core/ir.py` and `core/diagnostics.py` are written in full by the bootstrap
script, and they're the only files all four of you depend on.

**Freeze them at the end of Day 0.** After that, changing a field means all
four people agree in standup first. Not because ceremony is good, but because
Dev C's executor, Dev B's planner and Dev D's renderer all destructure those
dataclasses — a rename at 11pm Thursday breaks three branches at once.

Note that `core/ir.py` puts a `Position` on **every node**. This is the single
decision you cannot walk back. Diagnostics without line numbers are just
"something's wrong somewhere," and retrofitting positions means rewriting the
parser and builder. It costs you nothing on Day 1 and saves the project on
Day 4.

---

## 2. Where each feature lives

| Feature from the brief | Directory | Entry point |
|---|---|---|
| "analyse any project we pull or create" | `analyzer/` | `analyzer/project.py::analyze()` |
| "go look for the yml files" | `analyzer/discover.py` | `discover_flows(root)` |
| Gen-Z conventions | `parser/aliases.yml` + `parser/aliases.py` | `normalize(node)` |
| "check the standards / the way it is written" | `validation/` | `pipeline.py::validate_file()` |
| "show a message that the .yml is not correct" | `reporting/render.py` | `render_diagnostics(bag)` |
| `${{ }}` support | `expressions/` | `parser.py::parse()` + `evaluator.py::evaluate()` |
| `needs:` / matrix / parallelism | `planner/` | `plan.py` |
| Docker + the project's Dockerfile | `executor/` | `docker_backend.py` |
| WSL / Windows / macOS handling | `executor/paths.py`, `platform_.py` | isolated on purpose |
| "run whenever we upload/create a project" | `triggers/` | `watcher.py`, `hooks.py` |

Notice the cross-platform code lives in exactly two files. That's deliberate —
when your Windows teammate hits a path bug, they know where to go, and nobody
else's module is full of `if sys.platform ==` branches.

---

## 3. The pipeline, traced end to end

This is what actually happens when someone types `yeet run`. Six stages, each
one a pure function of the last. Print this and pin it above your desk.

```
                        cli/cmd_run.py
                              │
      ┌───────────────────────┼───────────────────────┐
      ▼                       ▼                       ▼
 ① ANALYZE             ② PARSE                  ③ VALIDATE
 analyzer/             parser/                  validation/
      │                       │                       │
 Path("~/proj")        Path(flow.yml)          Workflow + raw tree
      ↓                       ↓                       ↓
   Project              Workflow (IR)           DiagnosticBag
                                                      │
                                          errors? ────┴──── none?
                                              │              │
                                     render + exit 2         ▼
                                                        ④ PLAN
                                                        planner/
                                                             │
                                                    Workflow → ExecutionPlan
                                                             ↓
                                                        ⑤ EXECUTE
                                                        executor/
                                                             │
                                                    plan → RunResult
                                                             ↓
                                                        ⑥ REPORT
                                                        reporting/ + storage/
```

### ① Analyze — `analyzer/project.py`

```python
project = analyze(Path.cwd())
# Project(root=..., flows=[Path(...), ...], ecosystems=[Ecosystem("python", ...)],
#         is_git=True, dockerfile=Path("Dockerfile") | None)
```

Three sub-steps in order: walk **up** for the root (`root.py`), walk **down**
for flow files (`discover.py`), read marker files for the stack
(`fingerprint.py`). No YAML is parsed yet — this stage only touches the
filesystem.

If `project.flows` is empty, this is where you stop and suggest
`yeet init --auto` rather than erroring.

### ② Parse — `parser/`

```python
data = load_with_positions(flow_path, bag)   # ruamel rt mode, keeps .lc
data = normalize(data)                        # bet → run, moves → steps, ...
wf   = build_workflow(data, flow_path, bag)   # dict tree → IR dataclasses
```

Three separate files because they fail differently and you'll want to test them
apart. `loader` emits E101–E103. `aliases` never fails — it's a pure key
rewrite. `builder` emits E204/E205 as it constructs each `Step`.

The critical detail in `builder.py`: every `Step(...)` you construct gets its
`pos=` from `data.lc.value(key)`. Do it as you build, not after.

### ③ Validate — `validation/pipeline.py`

```python
bag = validate_file(flow_path, strict=False, upto=4)
if bag.has_errors():
    print(render_diagnostics(bag))
    raise typer.Exit(2)          # nothing runs. this is the gate.
```

Layers run in order and **stop between layers, not within one**. If Layer 1
finds bad YAML there's no point schema-checking, so return. But if Layer 3
finds three broken `needs:` references, report all three — a user who fixes one
error per run will hate your tool.

`yeet run` runs layers 0–3 and blocks on errors; Layer 4 runs and prints but
never blocks. `yeet check` runs all five.

### ④ Plan — `planner/`

```python
plan = build_plan(wf, contexts)
# ExecutionPlan(waves=[[JobInstance("build", {"node": 18}), JobInstance("build", {"node": 20})],
#                      [JobInstance("deploy", {})]])
```

Matrix expansion first, then the DAG, then topological sort into waves. Jobs
inside a wave run in parallel; waves run in sequence.

`find_cycle()` does double duty — the scheduler needs it, and Layer 3 validation
calls the same function for `E302`. Write it once.

It lives in **`core/graph.py`**, not `planner/graph.py`: validation is tier 3 and
the planner is tier 4, so calling into the planner would be an upward import.
`planner/graph.py` is a ten-line `Job`-shaped adapter over it. Same function,
one tier lower. See [`adr/0007`](adr/0007-tier-rule-consequences.md).

### ⑤ Execute — `executor/`

```python
for wave in plan.waves:
    results = run_parallel(backend.run_job, wave, max_workers=n)
    contexts.needs.update(results)      # downstream jobs see upstream outputs
```

Inside `docker_backend.run_job`, per job: resolve image → create **one**
container → for each step, write an LF script, `exec_run` it, stream output
through the masker, read back the state files → stop and remove the container
in a `finally`.

### ⑥ Report — `reporting/` + `storage/`

Live tree to the terminal via `reporting/console.py`, structured JSONL to
`.yeet/runs/<run-id>/` via `storage/runs.py`. `yeet logs` replays the JSONL,
which means your log format is tested every time anyone uses that command.

### The same pipeline, cut short

Every other command is a prefix of this one. That's why it's worth drawing.

| Command | Stages |
|---|---|
| `yeet scan` | ① + ② + ③ (layers 0–2 only) |
| `yeet check` | ① + ② + ③ (all 5 layers) |
| `yeet graph` | ① + ② + ③ + ④ |
| `yeet run` | all six |
| `yeet watch` | ① on change, then the rest |

Build the prefix first and every command downstream comes almost free.

---

## 4. Day 0, in order

Do these with all four of you in one room. It's three or four hours.

**1. ~~One person runs `bootstrap.py` and pushes.~~ Already done** — the skeleton
is in the repo and green. Everyone clones. Do not re-run the bootstrap script.

**2. Everyone gets a working env.**
```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pre-commit install
yeet --help                       # must print something
pytest -m "not docker"            # must pass (zero tests is passing)
```
Anyone whose env doesn't work by lunch is a blocker for the week — fix it now,
not Wednesday.

**3. Read `core/ir.py` and `core/diagnostics.py` together, out loud.** Argue
about field names now. Then freeze them and say so in the group chat.

**4. Set `git config core.autocrlf input`** on every machine. The
`.gitattributes` handles most of it, but the Windows and WSL machines need this
too. Skipping it is how you get the `$'\r': command not found` bug on Thursday.

**5. Agree the branch convention.**
```
main                      protected, PRs only, CI must be green
feat/<area>/<thing>       feat/analyzer/root-detection
fix/<area>/<thing>
docs/<thing>
```
Branch names start with your area, so `git branch -a` doubles as a status
board.

**6. Write ADR 0002–0006** (the list is in `docs/adr/0001`). Twenty minutes
each, split between you. These become your presentation's "why" slides.

**7. Open one issue per stub file**, assigned to its owner. The stub headers
already say who owns what — the bootstrap wrote that in.

---

## 5. The walking skeleton: your Day 1 target

Don't build subsystems bottom-up in isolation. Build the thinnest possible
vertical slice that touches every stage, then fatten it.

**Day 1 target:** `yeet run` works end to end for exactly this file:

```yaml
vibe: hello
when:
  push: {}
the_grind:
  build:
    cooked_on: ubuntu-latest
    moves:
      - bet: echo "we are so back"
```

No matrix. No `needs`. No expressions. No `uses`. One job, one step. Every
stage of the pipeline does its dumbest possible thing — the analyzer finds one
file, the parser handles four keys, validation runs Layer 0 only, the planner
returns one wave of one job, the executor runs one container.

Once that green line exists, everyone widens their own stage independently and
the smoke test tells you instantly who broke it. Teams that build the parser
fully, then the validator fully, then start on Docker on Wednesday, discover on
Thursday that nothing connects.

Wire the smoke test on Day 1 and let it stay red for two days:

```python
# tests/e2e/test_walking_skeleton.py
@pytest.mark.docker
def test_hello_world_runs(tmp_path):
    (tmp_path / ".yeet" / "flows").mkdir(parents=True)
    (tmp_path / ".yeet" / "flows" / "main.yml").write_text(HELLO, newline="\n")
    result = run_cli(["run", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "we are so back" in result.stdout
```

---

## 6. First six commits

In this order. Each is small, each is mergeable, each unblocks someone.

| # | Commit | Who | Unblocks |
|---|---|---|---|
| 1 | `chore: day 0 skeleton` | whoever ran bootstrap | everyone |
| 2 | `feat(core): freeze IR and Diagnostic contracts` | pair on it | everyone |
| 3 | `feat(reporting): diagnostic renderer with code frames` | D | anyone who wants to *see* an error |
| 4 | `feat(analyzer): find project root and discover flows` | A | test fixtures for everyone |
| 5 | `feat(parser): ruamel loader with positions + alias normalize` | A | B and D |
| 6 | `feat(executor): run one container, exec one step` | C | the walking skeleton |

Commits 3 and 4 look low-priority and aren't. The renderer means every
subsequent bug you hit prints legibly instead of as a stack trace, and the
analyzer means everyone can point their code at real repos on Day 2 instead of
hand-writing fixtures.

---

## 7. Avoiding the Thursday merge disaster

**Files more than one person will touch** — there are only four, so treat them
carefully:

- `cli/app.py` — one line per subcommand registration. Add your line, don't
  reformat the file.
- `core/codes.py` — append rows to `RULES`, always at the end of your layer's
  block. Appends merge cleanly; reordering doesn't.
- `parser/aliases.yml` — append only.
- `pyproject.toml` dependencies — announce in chat before adding one.

Everything else has exactly one owner. If you find yourself editing someone
else's directory, that's the signal to ask them for a function instead.

**Two habits worth enforcing:**

Rebase, don't merge: `git pull --rebase origin main` before every push. Four
people merging `main` into their branches produces a commit graph nobody can
read by Wednesday.

Merge to `main` daily, even if incomplete. A stub that raises
`NotImplementedError` merged on Tuesday is better than a perfect module merged
on Friday — because the former lets someone else import it and start work.

---

## 8. Quick reference: running things during development

```bash
yeet scan ~/some/repo             # does discovery work?
yeet check tests/invalid/E301.yml # does one rule fire correctly?
yeet check . --format json        # machine output
yeet run --path ~/demo -v         # the real thing

pytest -m "not docker"            # fast loop — run this constantly
pytest -m docker                  # needs the daemon
pytest tests/invalid -x           # every rule fires?
ruff check src tests --fix
lint-imports                      # tier rule — run before every push
mypy src
```

Add a `Makefile` (or `just` recipes) on Day 1 so `make check` runs the last
four. It's ten lines and it's the difference between everyone running the
linters and nobody running them.

---

## 9. Two things people will get wrong in the first 48 hours

**Someone will `print()` an error.** It'll be in a hurry, it'll be a
`print(f"bad key: {k}")` in the parser, and it will still be there on Friday
when the demo shows an unformatted line in the middle of a nice report.
Everything user-facing goes through a `Diagnostic`. Add a CI grep for
`print(` under `src/` if you have to.

**Someone will build a subsystem "properly" before connecting it.** Usually the
expression engine, because it's the most fun. A perfect Pratt parser that
nothing calls is worth less on Friday than a crude one wired into the pipeline.
The walking skeleton on Day 1 is what prevents this — hold each other to it.