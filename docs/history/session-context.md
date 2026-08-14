# yeet — session context log

**What this is.** The developers' own record of each build session: what was
delivered, how it was verified, and what was handed off or left open. Written
while the work was happening. **Newest entries are at the bottom.** Not a
tutorial — start at the [`README`](../../README.md) or the
[`handbook`](../handbook.md) for that.

## Session index

| # | Who · what | Highlights |
|---|---|---|
| 1 | DEV-C — the executor | Day-2 ship target met; the exec trap, masking chokepoint, exit codes |
| 2 | DEV-D — reporting, validation, secrets, storage, triggers | 6 CLI commands wired, 54 tests |
| 3 | DEV-A — analyzer, parser, actions, templates | `yeet scan` works end to end |
| 4 | DEV-B — expressions, planner, layer 3 | CSV table, matrix, fail-fast; 4 documented deviations |
| 5 | Integration — connecting the four subsystems | the dialect bug fixed; all carried-over defects closed |
| 3.1 | DEV-A — cut `loot:`/`stash:`, widen schema, fill corpus | 9 real workflows in `tests/corpus/` |
| 2.2 | DEV-D — ASCII-only TUI rework | no Powerline glyphs; fixed a real ordering bug |
| 7 | Discovery, E106, Layer 3, `uses:`, per-project Docker | corpus 9/9, all gates green |

## Session 1 — DEV-C: the executor

- **Shipped.** The whole executor package (~2,400 lines): Docker + local
  backends, wave-ordered runner, per-step loop with the single masking
  chokepoint, script/env/interpolate/images/workspace, plus `cmd_run` wiring.
  185 tests (167 fast + 18 Docker). All five CI gates green.
- **Verified live.** Day-2 target demonstrated in a container: three steps in
  one container, `$GITHUB_ENV` round-trip, planted secret + base64 redacted,
  stdout/stderr kept apart, bind mount writable both ways. Exit codes, SIGINT
  cleanup, daemon-unreachable → exit 3, bare repo → the sanctioned red state.
- **Worth knowing.** The exec trap was real: `exec_run(stream=True)` returns
  `exit_code=None`, so a naive runner reports every step as passing — fixed
  via the low-level `exec_create/exec_start/exec_inspect` path. Own-code
  defects the tests caught: `slug("..")` escaped the run dir; step labels
  leaked the whole multi-line script into the group header (`label()` now does
  "Run <first line>", as GitHub does).
- **Outstanding.** Two machine commands still open (`git config core.autocrlf
  input`, `pre-commit install`); three decisions for the owners (publish the
  base image?, a CI Docker job?, the `base_env` contract with Dev B); C15/C16
  and five `yeet run` seams waiting on Dev A/D — each marked in-file so nobody
  has to hunt.

## Session 2 — DEV-D: reporting, validation, secrets, triggers

- **Shipped.** `reporting/` (theme, code-frame renderer, `RunConsole`, JSON,
  SARIF), `validation/` (layer 0, 5-layer `pipeline`, layer-4 lints),
  `core/` (code registry, config), storage/secrets/triggers (`store`, `runs`,
  `artifacts`, `cache`, `watcher`, `hooks`), six CLI commands, ADRs 0002–0006,
  54 tests.
- **Verified.** All 5 gates green; frozen contracts and tiers untouched; no new
  dependencies.
- **Worth knowing.** A duplicated restatement of the same component list was
  removed from this entry — the list above is the single source.

## Session 3 — DEV-A: analyzer, parser, actions, templates

- **Shipped (A3–A20).**
  - Analyzer: root walk-up, marker→ecosystem table, depth/inode-safe flow
    discovery, fingerprint version pinning, `project.analyze()`.
  - Parser: ruamel loader (E101–E104, W105), alias rewrite, canonical schema,
    layer-2 validation with did-you-mean (E201–E208), dict→IR builder.
  - Actions: local composite + remote `owner/repo@ref` resolver (E313/E314/W319).
  - Templates + CLI: per-ecosystem `init --auto`, bundled checkout action,
    `--no-color`, `yeet scan` report.
- **Verified.** Golden fixtures (9) + one-code-per-fixture invalid set (14);
  `yeet scan` end to end; each fixture fires exactly its own code.
- **Blockers.** `yeet check`/per-flow validity/offline run depend on Dev D's
  `pipeline` and Dev C's executor, both still stubs. Net: 224 passed, 37 skipped.

## Session 4 — DEV-B: expressions, planner, layer 3

- **Shipped.** `expressions/` (byte-offset lexer, Pratt parser, 11 contexts,
  GitHub-loose evaluator, 12 functions — CSV engine table passes), `planner/`
  (matrix expansion, `build_plan` → waves), `core/graph.py`
  (`find_cycle`/`topo_waves`, shared by validation and planner per ADR 0007),
  layer 3 (E301–E312), `cmd_graph` ASCII render. 511 passed, gates green.
- **Deliberate deviations, all documented in code:** matrix order (GitHub does
  exclude before include), `if:` evaluated at run time not plan time, and
  skip/fail-fast living in the runner, not the planner.
- **Hand-offs.** Dev A: builder/analyzer/suggest; Dev C: interpolate
  degradation; Dev D: remaining L3 codes (E304–E308, E313–E317, W318).

## Session 5 — integration

- **The headline bug.** `yeet check` failed its own flagship example with five
  errors: `aliases.normalize()` had **zero call sites** in the product — the
  golden tests called it by hand. Wired into `pipeline.py`; the dialect works.
- **Two more "written but not wired":** layer-4 lints never ran (`RULES` was
  `[]` — the rule modules were never imported) and `yeet logs` could never find
  a run (`RunStore` was never constructed). The shape was identical in all
  three: a module with passing tests and no caller. The handbook now says it:
  **when you finish a module, grep for its call site.**
- **Defects fixed while wiring:** W403 firing on `runs-on:` labels, a broken
  `post-commit` hook shim (`--sha`), `hooks install` clobbering user hooks, CI
  living in the wrong directory (never ran), and `${{ secrets.X }}` resolving
  to empty.
- **Carried-over defects from `undone.md` — all closed:** dead seams removed
  (wrappers, `EchoSink`, `EXIT_NOT_READY`, `NotImplementedError` branches),
  `pipeline` exceptions → real `YEET-E900` errors, code-title drift corrected,
  secrets now Fernet-encrypted, watcher rewritten on watchdog with a lock.
- **Gate hardened.** `make check` gained `format` and `noprint`; CI runs the
  identical set plus rules-doc and Docker jobs. +66 tests (walking skeleton,
  dialect parity, lint registration, secrets, watcher).
- **For standup:** `architecture.md` needs an accuracy pass; `tests/corpus/`
  was still empty at this point; the Docker CI job is a reversible call;
  plan.md §2.4/§2.5 still open.

## Session 3.1 — DEV-A: cut `loot:`/`stash:`, widen schema, fill corpus

- **Cut** `loot:`/`stash:` from the alias table — they mapped to
  `artifacts:`/`cache:`, not canonical GitHub Actions keys, so an alias would
  validate clean and silently do nothing at runtime. Updated handbook,
  architecture, and the storage docstrings.
- **Widened** the schema for real-world syntax: `run-name`, `permissions`,
  `concurrency`, `services`, `continue-on-error`; scalar/expression `env` and
  `timeout-minutes`.
- **Filled** `tests/corpus/` with 9 real OSS workflows (with provenance) plus
  a parametrized test: parses clean, builds IR, ≥80% success floor.
- **Gate:** 5/5 green, 682 tests.

## Session 2.2 — DEV-D: ASCII-only TUI rework

- Replaced every Unicode glyph the renderer printed with ASCII: `[OK]`/`[FAIL]`
  /`[SKIP]` symbols, `>` running marker, `+--`/`\--` tree branches, `>>` group
  marker. Dropped `rich.tree`/`spinner` (both Unicode-only) for a hand-rolled
  ASCII tree — which also closes a real crash risk on legacy Windows codepages.
- Fixed a real ordering bug along the way: the footer printed the status icon
  before the branch; now it matches the header's branch-then-icon order.
- **Verified.** Live forced-TTY smoke test + a real piped run; 683 tests and
  all gates green.

## Session 7 — discovery, dialect, Layer 3, `uses:`, per-project Docker

Five threads, one theme: things that were written, tested, and not reachable.

- **Gate.** Started from a red HEAD — an orphaned `_win_pid_alive()` from a bad
  merge conflict; fixed.
- **Discovery.** Flows now match at any depth (`workflows/ci.yml` under any
  ancestor), `.yml`/`.yaml` alike; `yeet scan` sees what was invisible before.
- **E106.** The one case that cannot work — the same key in both dialect and
  canonical spellings — now refused instead of silently dropping one.
- **Layer 3 finished.** E304–E308, E316, W318 shipped (E304 retitled to the
  reachable "duplicate step id", E307 takes store names from `cmd_run`, E316
  deliberately narrow).
- **`uses:` runs.** A17 landed four sessions earlier; now composites are
  inlined, `upload-artifact`/`cache`/`download-artifact` work against
  `storage/`, and docker/node actions skip with a reason.
- **Per-project Docker.** Image pulls serialized per reference (one pull for a
  5-leg matrix), `project_slug` namespaces images and containers, `yeet prune`
  is project-scoped.
- **Verified.** `make check` 787 passed; corpus 9/9 validate clean (was 6/9);
  full end-to-end runs across four layouts × both dialects.
