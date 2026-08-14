# yeet — session review log

**What this is.** The independent review of every build session: what it
shipped, whether it held up against the project's standards, and what it left
open or broke. Written as the work happened — **newest work is at the bottom.**
Not a tutorial — start at the [`README`](../../README.md) or the
[`handbook`](../handbook.md) for that.

## Session index

| # | Who · what | Verdict at the time |
|---|---|---|
| 1 | DEV-C — the executor (Docker/local backends, runner, steps, images) | strong; the "delete the seam" instructions went unexecuted |
| 1.1 | DEV-C update — three-OS CI green, PR #1 open | the Windows bug class, all four instances |
| 2 | DEV-D — reporting, validation, secrets, storage, triggers | idiomatic; 3 gaps (lints unreachable, secrets unencrypted, code drift) |
| 2.1 | DEV-A task — flexible `workflows/` discovery | assignment |
| 3 | DEV-A — analyzer, parser, actions, templates, CLI | strong; codes.py titles drift again |
| 4 | DEV-B — expressions, planner, layer 3 | best so far; tree committed red (forgot `make fix`) |
| 5 | Integration — wires the four subsystems together | closed every carried-over defect |
| 6 | DEV-C — the contexts (matrix/env/needs/steps/runner/job) | fixed the class, not the instance |
| 6b | Windows CI, round one | two real product bugs found and fixed |
| 6c | Windows CI, round two | first fully green 3-OS CI run in the project's life |
| 7 | Discovery at any depth, E106, Layer 3, `uses:`, per-project Docker | corpus 9/9, gates green |
| 8 | Packaging — repo root, installer, Python 3.10 floor, secrets import | clone + install finally work |

**How to read an entry.** *What changed* → *verified against the standards*
(run, not asserted) → *defects found* → *verdict*. Cross-check with `make
check` and `pytest`; don't take a claim on trust.

## Product requirements behind the build

Each one is why a subsystem exists:

- Runs on **LTS Python** (3.10+; Ubuntu 22.04 LTS ships it).
- Installer is **compatible and has a good TUI** while installing.
- **Jobs run clean**, without errors.
- **Secrets and variables are imported to the local machine**, stored in
  `.env`, and fetched when a job runs — `yeet secrets import` then `yeet run`.
- The **TUI is good both at install time and at run time**.

---

## Session 1 — DEV-C: the executor

**Verified.** Every claim reproduced — the exec trap is real (the low-level
`exec_create → exec_start(stream, demux) → exec_inspect` dance because
`exec_run(stream=True)` returns `exit_code=None`); the exit-42 test passes
against a live daemon. Gates green at his commit; frozen contracts, tiers, and
the masking chokepoint all held; zero new dependencies. First-class work.

**Defects found.**
1. Stale seams: every seam Dev C carved out has landed, yet `cmd_run` still
   carries the five `_stage` wrappers + `EchoSink`. The wrappers now only
   mislead — delete them with `EXIT_NOT_READY` (which collides with
   `EXIT_JOB_FAILED=1`).
3. `interpolate.py`'s degradation path is dead since Dev B landed B4/B6.
4. `env.py::github_env` has no call site — the executor's `GITHUB_*` env and
   Dev B's context are not actually wired together.

**Bottom line.** Strongest, most honestly-documented session so far. The only
real smell: every "delete me when X lands" seam is still there after X landed.

## Session 1.1 — DEV-C update: all eight CI jobs pass

All eight CI jobs pass — the **first fully green CI run** in the project's
life. It took four rounds, each a real product bug:

1. `script_suffix` ignored the platform default (every Windows job flopped).
2. `bash` on Windows is the WSL launcher, not a shell.
3. Probing a pid **killed** it on Windows (`os.kill(pid, 0)` → `TerminateProcess`).
4. mypy couldn't be green on all three OSes at once (`ctypes.windll`).

One shape underneath all of them: a function that behaves differently on
Windows, called as if it didn't. PR #1 open and mergeable. **DEV-C: complete.**
Remaining C items: C15/C16 and the executor half of `loot:`/`stash:`.

## Session 2 — DEV-D: reporting, validation, secrets, triggers

**Verified.** All 5 gates green; frozen contracts, tiers, §4 signatures, and
the merge protocol held; no new dependencies. Idiomatic, well-organized work.

**Defects found.**
1. **Layer-4 lints never fire in production** — rules self-register at import
   but nothing imports the rule modules (`RULES` is empty at runtime; tests
   pass only because `test_lint.py` imports them directly).
2. `yeet check` does nothing end to end (layers 1–3 still stubs; the
   sanctioned red state, but the session-context overstates it).
3. **Secrets are stored in plaintext JSON** — direct violation of D21/
   architecture §5 (Fernet + scrypt + keyring required); the `cryptography` dep
   is unused.
4. Diagnostic-code semantics drift from the design doc (E206/E208 swapped, and
   more) — a standup alignment needed before Dev B builds against `codes.py`.
5. Minor: `run_lints` docstring wrong about `--strict`; `pipeline.py` swallows
   real exceptions.
6. Watcher is a polling loop, not the watchdog observer; wrong signatures;
   `print()` where a hook should be.

**Bottom line.** Solid, idiomatic work that respects every discipline — but it
stops short of its own claims in three places: the lint layer isn't reachable,
secrets aren't encrypted, and the registry silently redefined the Layer-3
contract.

## Session 2.1 — DEV-A task: flexible `workflows/` discovery

A task, not a subsystem: let a workflow live at the project root in a
`workflows/` folder under any filename. Precedence becomes `.yeet/flows/` (0)
→ `.github/workflows/` (1) → `workflows/` (2) → root `yeet.yml` (3), in the
same three files. Done when `yeet scan`, `check`, and `graph` all discover
`workflows/flows.yml`.

## Session 3 — DEV-A: analyzer, parser, actions, templates

**Verified.** The pipeline builds the IR end to end; each invalid fixture fires
exactly its own code; position discipline survives the whole chain (code frames
point at the exact line); `yeet scan` works live. Tier-clean, no new deps.

**Defects found.**
1. **codes.py titles drift** (same class as session-2 finding #4): E206/E208/
   E313/E314/W319 contradict what layer2 and the resolver actually emit —
   `rules.md` and `yeet explain` tell users the wrong thing.
2. Layer-4 lints still dead at runtime (unfixed from session 2, now
   load-bearing) — `yeet check` on `actions/checkout@main` prints nothing.
3. Two dead seams left behind now that the layers are real.

**Bottom line.** Strongest session so far — the handed-off seams are all real
and verified. Two things to fix: the code titles, and the lint-layer imports.

## Session 4 — DEV-B: expressions, planner, layer 3

**Verified.** Dev B's own suite passes; behavior verified live, not asserted
(matrix, topo waves, cycle path, layer-3 codes, `yeet graph` exit codes);
tier rule respected AND documented (core/graph at tier 0 per ADR 0007); codes
align with the registry this time; documented deviations are real ones.

**Defects found.**
1. **"Status: complete and green" is false for the committed tree** — the gate
   is red at HEAD (ruff format on 10 files, 7 of them Dev B's). A 30-second
   `make fix`, but CI would fail on the first push.
2. "511 passed" doesn't match HEAD (605 today) — numbers diverged.
3. Dead seam: `cmd_graph`'s "parser is not ready" fallback is unreachable.
4. Carried over (not Dev B's): L4 lints, `pipeline` swallowing, code titles.

**Bottom line.** The highest-quality session to date — except the tree was
committed without `make fix`, so the exact gate it claims green is red.

## Session 5 — integration

Not a subsystem session: it connected the four that existed, closed every
carried-over defect, and added the missing docs.

- **Fixed (previous defects):** all session 1–4 defects above — the five
  wrappers + `EchoSink` + `EXIT_NOT_READY`, interpolate's dead degradation,
  L4 lints (package `__init__` now imports the rule modules), secrets→Fernet,
  code-title drift, watcher, the E900 swallow-fix, `make check` + `format`.
- **New defects found (all fixed):**
  1. `aliases.normalize()` had no call site — the dialect failed its own
     validator; four sessions of review missed it because the golden tests call
     it by hand.
  2. `RunStore` was never constructed — `yeet logs` never found a run.
  3. W403 fired on `runs-on:` labels.
  4. The `post-commit` hook shim passed a bogus `--sha`.
  5. `hooks install` clobbered pre-existing user hooks.
  6. CI had never run — workflows lived one directory too deep.
  7. `RunConsole` emitted the group header before the job header.
  8. `${{ secrets.X }}` always evaluated to empty — the nastiest, because the
     symptom (no secret in the log) is exactly what success looks like.
- **Still open, deliberately:** `github_env` has no call site; L3 codes
  E304–E308/E313–E317/W318 unimplemented; `tests/corpus/` empty; C15/C16
  seams; `architecture.md` drifted.
- **Verified.** All gates green, 671 passed, full end-to-end on a scratch repo,
  both spellings, `yeet run` → "we are so back".
- **Hand-offs.** DEV-C: thread per-instance `Contexts` through the runner (the
  highest-value fix in the repo). DEV-A: decide loot/stash; fill `tests/corpus/`.
  DEV-B: finish Layer 3. DEV-D: commit + get CI green. Everyone: make "grep for
  the call site" a PR checklist item.

## Session 6 — DEV-C: the contexts

The bug session 5 named "the nastiest of the set" had five more instances of
itself. This session **fixed the class, not the instance**.

- **Broken.** `cmd_run` built ONE `Contexts` for the whole run (filled three of
  ten fields). `matrix`, `env`, `needs`, `steps`, `runner`, and `job` were
  therefore empty in every leg that ever ran. Worse: `Workflow.env` was parsed
  and dropped on the floor, and `github_env` still had no call site.
- **Done.** New `executor/contexts.py` builds a fresh `Contexts` per job
  instance and per step (never mutates the shared base — no cross-leg races);
  `github_env` merged into every job env; `${{ github.run_id }}` and the log
  dir stay in sync; expressions speak GitHub's result vocabulary
  (`success`/`failure`/`skipped`/`cancelled`, not `slayed`/`flopped`).
- **Verified.** `make check` + 686 tests green; all contexts resolve live in
  containers, each matrix leg printing its own value. **The tripwire was
  checked by breaking it** — the reverting test fails, which is why the bug
  lived through four review sessions.
- **Still open.** loot/stash aliases vs schema; C15/C16; L3 codes; empty
  corpus; CI uncommitted; duplicate job header on matrix legs.

## Session 6b — Windows CI, round one

First CI run in the project's life: everything green **except windows-latest**.
Two distinct causes, both fixed.

1. **`script_suffix` ignored the platform default** — every un-shelled step was
   written to `.sh` and invoked as `pwsh -File` (which runs `.ps1` only). Fixed
   by a single `resolve_shell` both functions call. Shape worth naming: two
   functions deriving the same default independently.
2. **The e2e harness decoded child output with the wrong codec** — `text=True`
   decoded UTF-8 output as cp1252 and four tests died. Now
   `encoding="utf-8", errors="replace"`.
3. Bash-specific e2e steps now say `shell: bash` — the walking skeleton keeps
   the default shell so the pwsh path stays exercised.

Windows itself is verified by CI, not locally — macOS cannot prove it.
**DEV-C status:** contexts + the Windows shell pair complete; C15/C16 + the
executor half of loot/stash remain.

## Session 6c — Windows CI, round two

`shell: bash` reached the WSL launcher (a bash that isn't a shell);
`platform_.shell_executable()` now finds Git for Windows. Then:
**probing a pid killed it** — `ProjectLock` used `os.kill(pid, 0)`, which on
Windows calls `TerminateProcess`; a stale `watch.lock` could kill an unrelated
process on a user's machine. `platform_.pid_alive()` now owns it.
And mypy: no `# type: ignore` spelling is green on all three OSes at once;
`getattr(ctypes, "windll")` needs none.

**Result.** CI run all 8 jobs green — the first time in the project's life.
Lesson: every Windows bug was a function that behaves differently there, called
as if it did not.

## Session 7 — discovery at any depth, E106, Layer 3, `uses:`, per-project Docker

**The pattern.** Six times a module was written, unit-tested, reviewed, and
never called (aliases, RunStore, L4 rules, Contexts, actions/resolver,
storage/artifacts+cache). Unit tests were green throughout — a test that calls
the module directly can't notice nothing else does.

**Defects only reachable once the code was:**
1. `restore-keys` did no prefix matching (hashing destroyed the prefixes).
2. `arcname=p.name` flattened cached paths (`src/dist` and `web/dist` both
   became `dist`).
3. `extractall` without `filter="data"` — tarball path traversal.
4. `path: dist/**` stored nothing (a trailing `**` matches directories only).
5. E305 fired on `${{ env.cache-name }}` — the `env` context is a map lookup,
   not a shell export.
6. E303 rejected include-only matrices, and `matrix.expand()` collapsed them
   into ONE unparameterised job that reported success for all nine versions.

Corpus went from 6/9 to 9/9 validating clean.

**Still open.** C15/C16; remote node actions skipped; W317 unimplemented;
built-ins run on the host (deliberate, documented); `prune --all` needed for
pre-hash images; the terminal UI is another developer's thread.

**Verified.** `make check` 787 passed, six gates green, 18 docker tests
against a live daemon.

## Session 8 — clone, install, run

**The clone didn't work, and it's the first thing anyone tries.** `pip install
.` and `pip install git+<url>` both failed — the Python project lived one
directory down in `yeet/`. Moved to the repo root with `git mv`; CI drops
`working-directory: yeet`; the two near-duplicate READMEs collapse into one.

**Python floor to 3.10.** Ubuntu 22.04 ships 3.10 and is the default WSL
image; `tomllib` (3.11 stdlib) → `tomli` behind a `sys.version_info` branch
mypy can see. Lesson: a version-dependent construct needs a version check the
type-checker can see — twice now.

**Defects found by running on 3.10, not by reading:**
1. `with:` was never interpolated for built-in actions — a two-leg matrix
   uploaded both artifacts under one literal name.
2. `Live` cropped the bottom of the tree (`vertical_overflow` defaulted to
   "ellipsis", hiding exactly the running step the view exists to show).
3. `Contexts.vars` was never populated — the same disease `secrets` had in
   session 5, and the seventh instance of the class.

**Secrets and variables.** `yeet secrets import` reads the workflows, finds
every `${{ secrets.* }}` / `${{ vars.* }}`, writes them to `.env`, fills in
whatever the shell exports, never overwrites. Local pool: one set of values,
and only the workflow says which are secret — mask a variable or leak a secret
and both failure modes now have a passing e2e tripwire.

**Still open.** C15/C16; built-ins run on the host (deliberate); W317;
installer assumes git; `docs/` overlap; Windows verified by CI only; the live
resume TUI is another thread.

**Verified.** `make check` 797 passed, six gates green; full suite green on a
real 3.10 interpreter; end to end from an empty `$HOME`: `install.sh` →
`secrets import` → `run`, with the secret reaching the step and the token
nowhere in the logs.