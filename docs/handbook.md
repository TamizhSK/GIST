# yeet — the team handbook

**Read this first. It is the only document you must read end to end.**
Twenty minutes, and you will know what the tool does, how a command travels
through the code, where your change belongs, and what "done" looks like.

The other documents, and when to open them:

| Document | What it is | Open it when |
|---|---|---|
| **this file** | orientation, commands, working style | now, and whenever you're lost |
| [`understanding-yeet.md`](understanding-yeet.md) | the same system as diagrams, plus a reading order | you are new, or onboarding someone |
| [`architecture.md`](architecture.md) | the 1,000-line design rationale | you want to know *why* a subsystem is the way it is |
| [`getting-started.md`](getting-started.md) | Day-0 machine setup | your environment is broken |
| [`rules.md`](rules.md) | every diagnostic code — **generated** | a code fires and you don't know what it means |
| [`adr/`](adr/) | the eight decisions we can't relitigate casually | you're about to argue with one of them |
| [`../plan.md`](plan.md) | who owns what, day by day | you need your next task |

---

## 1. What yeet is, in one paragraph

**yeet runs GitHub Actions workflows on your laptop, in Docker, and tells you
what's wrong with them before it runs anything.** It parses canonical GitHub
Actions YAML *and* a friendlier dialect of its own (`vibe:` for `name:`,
`the_grind:` for `jobs:`), validates through five layers that produce
rustc-style code frames, plans the job DAG, and executes each job in one
container with one `exec` per step. It is a superset, not a replacement: a real
`.github/workflows/ci.yml` runs unchanged.

The three things it does, in the order the demo shows them:

```
yeet scan     what is this project, and what workflows does it have?
yeet check    is this workflow correct?   ← works with no Docker at all
yeet run      run it.
```

---

## 2. The dialect

One parser. It parses canonical GitHub Actions. The dialect is a **key-rewrite
pass** applied immediately after the YAML loads, driven by a flat table in
`src/yeet/parser/aliases.yml`. Adding an alias costs one line and zero code.

```yaml
vibe: hello                    # name:
when: {push: {}}               # on:
the_grind:                     # jobs:
  build:
    cooked_on: ubuntu-latest   # runs-on:
    moves:                     # steps:
      - bet: echo "we are so back"   # run:
```

Both spellings produce byte-identical IR — `tests/unit/test_dialect_parity.py`
asserts exactly that, through the real entry point.

Full table: `vibe`→name, `when`→on, `the_grind`/`missions`→jobs,
`cooked_on`→runs-on, `moves`→steps, `bet`/`cook`→run, `yoink`/`borrow`→uses,
`after`/`waits_for`→needs, `only_if`/`no_cap_if`→if, `drip`→env, `tea`→secrets,
`squad`→strategy, `multiverse`→matrix, `patience`→timeout-minutes,
`delulu`/`its_fine`→continue-on-error, `where`→working-directory.

Status vocabulary in output: **slayed** (success) · **flopped** (failure) ·
**mid** (partial) · **cooked** (running) · **skipped (not the vibe)**.

---

## 3. The one architectural rule

**Imports only ever point downhill.** Every directory has a tier. A module may
import from lower tiers and never from a higher one or a sibling on the same
line. `lint-imports` enforces this on every push; it is not a convention.

```
tier 7   cli                                  ← the only tier that may import anything
tier 6   triggers
tier 5   executor  |  storage  |  secrets     ← siblings: MAY NOT import each other
tier 4   planner
tier 3   validation
tier 2   parser  |  analyzer  |  actions      ← siblings
tier 1   expressions  |  reporting            ← siblings
tier 0   core                                 ← imports nothing from us. Ever.
```

**When the rule blocks you, push the pure part down into `core/` and leave the
policy up top.** That single move is the answer to all five problems it caused,
and each indirection turned out to be worth having anyway:

| The problem | The move |
|---|---|
| executor needs masking, `secrets/` is a sibling | `core/masking.py` — pure `Masker` |
| executor needs to write logs, `storage/` is a sibling | `core/events.py` — `LogSink` protocol, inverted |
| the `scan` renderer needs `Project`, `analyzer/` is above it | `core/project.py` |
| layer 3 and the planner both need cycle detection | `core/graph.py` — plain `{node: [deps]}`, no IR |
| `actions/` "runs" steps but the executor consumes it | `actions/` resolves to IR, executes nothing; sits at tier 2 |

`core/` is closed. A sixth addition needs all four of us to agree.
`core/ir.py` and `core/diagnostics.py` are **frozen** — changing a field means
a standup, because the planner, executor and renderer all destructure them.

---

## 4. How a command actually travels through the code

This is the part worth understanding properly. `yeet run` is the whole pipeline;
every other command is a **prefix of it**.

```
yeet run
  │
  ├─ analyzer.project.analyze(root)                          tier 2
  │     root.py      walk UP for .git/.yeet/.github          → the project root
  │     discover.py  walk DOWN, bounded                      → flows, foreign CI
  │     fingerprint.py  markers → ecosystems                 → Project
  │
  ├─ validation.pipeline.validate_file(flow, upto=4)         tier 3  ◄── the gate
  │     layer 0  layer0_file.py   bytes: unreadable, empty, tabs, CRLF, BOM
  │     layer 1  layer1_yaml.py   → parser/loader.py: ruamel round-trip,
  │                                 duplicate keys, the `on:`→True trap
  │     ────────  parser/aliases.py::normalize()  ← THE DIALECT PASS
  │     layer 2  layer2_schema.py  jsonschema against the CANONICAL form
  │     ────────  parser/builder.py  dict tree → IR, positions set AS built
  │     layer 3  layer3_semantic.py  needs→unknown job, cycles, expressions
  │     layer 4  layer4_lint/       pinning, secrets, shell, portability
  │                                 → returns (DiagnosticBag, Workflow | None)
  │
  ├─ ERRORS?  render code frames, exit 2. NO CONTAINER HAS BEEN CREATED.
  │
  ├─ planner.plan.build_plan(workflow, contexts)             tier 4
  │     matrix.py  product → exclude → include   (GitHub's real order)
  │     graph.py   → core.graph.topo_waves       → ExecutionPlan(waves)
  │
  └─ executor.runner.run_plan(plan, backend, options)        tier 5
        one container per JOB, one `exec` per STEP
        steps.py   the single masking chokepoint — every LogEvent is born here
        → FanOut → RunConsole (live tree) + RunStore (JSONL for `yeet logs`)
```

Two seams are worth memorising:

- **`validate_file` returns `(bag, workflow)`.** That tuple is why `run` can
  validate and then plan without parsing twice, and why `check`, `scan` and
  `graph` are each about thirty lines.
- **`upto=N` is what makes each command a prefix.** `scan` uses `upto=2` (fast,
  no semantics), `check` uses `upto=4`, `run` uses `upto=4` and blocks only on
  errors.

### Where do I put this code?

| You are writing… | It goes in | Tier |
|---|---|---|
| a new diagnostic code | `core/codes.py` (append to **your layer's** block) | 0 |
| something everything needs, with no dependencies | `core/` — but ask first | 0 |
| terminal output, colors, code frames | `reporting/` | 1 |
| anything about `${{ }}` | `expressions/` | 1 |
| "what is this project" | `analyzer/` | 2 |
| YAML → IR | `parser/` | 2 |
| resolving a `uses:` to steps | `actions/` (resolves only, never executes) | 2 |
| a new check on a workflow | `validation/layerN_*.py` or `layer4_lint/` | 3 |
| matrix, DAG, waves | `planner/` | 4 |
| anything touching Docker or a subprocess | `executor/` | 5 |
| a new command | a new `cli/cmd_*.py` + one line in `cli/app.py` | 7 |

---

## 5. Every command

```bash
yeet scan [PATH]                 # what is this project? stack, markers, flows, validity
yeet check [PATH] [--strict] [--format pretty|json|sarif]
yeet run [FLOW] [--path DIR] [--job NAME] [--event push] [--jobs N]
         [--secret K=V] [-v]
yeet graph [PATH]                # the job DAG, matrix legs expanded, waves numbered
yeet explain YEET-E301           # what does this code mean
yeet init [--auto]               # generate a flow for the detected stack
yeet logs [RUN_ID]               # replay a past run through the live renderer
yeet watch [PATH] [--strict]     # revalidate on save; 500ms debounce, project lock
yeet prune                       # drop the build cache and .yeet/tmp
yeet hooks install [--blocking] [--force] | uninstall
yeet secrets set NAME | list | rm NAME
yeet --version | --no-color | --help
```

Global `--no-color` is honored everywhere, as is `NO_COLOR`.

### Exit codes — these are a contract, scripts depend on them

| Code | Meaning |
|---|---|
| 0 | slayed |
| 1 | the workflow ran and something in it failed |
| 2 | the workflow file is wrong — **nothing ran**. This is the gate. |
| 3 | no Docker daemon |

### A five-minute tour on any repo

```bash
cd ~/some/project
yeet scan                      # finds .github/workflows/*, prints the stack
yeet check                     # code frames, no Docker needed
yeet graph                     # the DAG on a projector
yeet run --job build -v        # -v prints the plan before executing
yeet logs                      # replay what just happened
```

---

## 6. Working style

### Your loop

```bash
make test        # fast — run this constantly (~6s, 671 tests)
make check       # ALL FIVE GATES — run before every push
make fix         # repairs what `check` complains about (ruff --fix + format)
```

`make check` is `lint · format · imports · types · noprint · test`, and it is
**exactly what CI runs**. That equality is load-bearing: it drifted twice, CI
gained `ruff format --check` while the Makefile didn't, and `main` was red both
times while everyone believed they had run the gate. If you add a gate, add it
in both places.

Other targets: `make image` (build the base container), `make docker` (the 18
container tests), `make rules` (regenerate `docs/rules.md` — never hand-edit it).

### Branching and merging

- `main` is protected. PRs only, CI green.
- Branch names: `feat/<area>/<thing>` — e.g. `feat/analyzer/root-detection`.
  Area first, so `git branch -a` doubles as a status board.
- **`git pull --rebase origin main` before every push.** Four people merging
  `main` into their branches produces a graph nobody can read by Wednesday.
- **Merge daily, even when incomplete.** A stub that raises merged Tuesday beats
  a perfect module merged Friday, because three other people can import it.

### The five shared files — touch with care

| File | Rule |
|---|---|
| `cli/app.py` | one registration line per command, appended. **Do not reformat.** |
| `core/codes.py` | append at the end of *your layer's* block. Appends merge; reordering doesn't. |
| `parser/aliases.yml` | append only |
| `pyproject.toml` deps | **announce in chat before adding one** |
| `core/ir.py`, `core/diagnostics.py` | frozen — a change needs all four of us |

Everything else has exactly one owner; see the `Owner:` line in the docstring at
the top of every file. **If you're editing someone else's directory, stop and
ask them for a function instead.**

### Conventions you will hit in the first hour

- **CLI options use `Annotated`**: `path: Annotated[Path, typer.Option("--path")] = Path()`.
  The classic style trips ruff's B008 on every parameter. A required argument
  has *no* default — `= ...` is classic-style and mypy rejects it.
- **`Status` and `Severity` stay `(str, Enum)`**, not `StrEnum`, with a
  `# noqa: UP042`. StrEnum changes what `str()` returns and three modules format
  those values.
- **Never `print()`.** User-facing output is a `Diagnostic` (validation) or
  `typer.echo`/`secho` (CLI). `make noprint` fails the build on a bare `print(`
  under `src/`, checked by AST so it doesn't trip on the word in a docstring.
- **Never `eval()`** for expressions. `expressions/` is a hand-rolled lexer and
  Pratt parser for exactly this reason.
- **Positions are set as each node is built**, in `builder.py`, from
  `data.lc.value(key)` — never retrofitted. Retrofitting is a parser rewrite.
- **Docstrings carry `Owner:` and `Tier:`.** Keep them accurate; the tier line
  is how you know what you're allowed to import.

### Writing a test

The suite is 671 fast tests plus 18 that need Docker (`@pytest.mark.docker`,
skipped automatically when the daemon is absent).

| Kind | Where | Convention |
|---|---|---|
| a rule fires | `tests/invalid/<CODE>.yml` | one file, broken in exactly one way, named for the code. A parametrized test asserts it emits **only** that code. |
| parser IR | `tests/fixtures/valid/<n>.yml` + `<n>.expected.json` | golden files |
| expressions | `tests/unit/data/expression_table.csv` | `expr, context, expected` rows |
| a subsystem | `tests/unit/test_*.py` | build IR by hand — `core/ir.py` is real and frozen |
| the whole pipeline | `tests/e2e/test_walking_skeleton.py` | drives the real CLI in a subprocess |

**The lesson that cost us three sessions:** a unit test that imports the thing
it tests can prove the thing works and still miss that *nothing calls it*. Both
of the two worst bugs found in this codebase were of exactly that shape —
`aliases.normalize()` with no call site, and lint rules that self-register on an
import nobody performed. Both had passing unit tests throughout. **When you
finish a module, grep for its call site.** If there isn't one, you are not done.

---

## 7. What is true today

Verified by running it, not asserted:

```
make check          all five gates green
pytest              671 passed, 18 docker tests deselected
lint-imports        2 contracts kept, 0 broken
mypy src            no issues in 101 source files
```

End to end, both spellings, no Docker required (`cooked_on: local`):

```
yeet scan → yeet check → yeet graph → yeet run → yeet logs
```

Known gaps, honestly:

- **Remote `uses:`** (`owner/repo@ref`) is implemented and unit-tested against a
  clone double, but has not been exercised against the real network.
- **Docker actions and JS actions** (`runs.using: docker|node20`) are seams:
  `steps.py` reports them and marks the step skipped rather than pretending.
- **Layer 3 codes E304–E308, E313–E317, W318** are registered but not all
  implemented; `layer3_semantic.py`'s docstring lists which.
- **`tests/corpus/`** is empty — the "% of real-world syntax supported" number
  in the demo needs 5–10 real OSS workflows dropped in there.

---

## 8. If you are stuck

1. `make check` — most confusion is a gate you haven't run.
2. `yeet explain YEET-E301` — every code has a section in `docs/rules.md`.
3. `YEET_DEBUG=1 yeet check <file>` — re-raises internal errors with a traceback
   instead of reporting them as `YEET-E900`.
4. The `Owner:` line in the docstring of the file you're in. Ask that person.
5. Blocked more than two hours? Escalate. Don't wait for the sync.
