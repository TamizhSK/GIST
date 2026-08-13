# session-1 work


My verification of DEV-C's session-1 work (commits a84b7b0 "feat: DEV-C session started" + 3b76594 "chore: DEV-C session context", 36 files, +4,473 lines). This is the executor, plan.md C2–C14 + C17, plus the `cmd_run` wiring it hangs on.

What changed
- executor/ — the whole package: backend.py (JobContext/Backend/DockerUnavailable), docker_backend.py (one container per job, exec per step), local_backend.py, runner.py (wave-ordered bounded pool, needs/fail-fast/skip logic), steps.py (the per-step loop, masking chokepoint), script.py, env.py, state_files.py, commands.py, interpolate.py, images.py (image resolution + E315), workspace.py (bind mount + layout + slug), paths.py, platform_.py, build.py, cmd_prune.py
- cli/cmd_run.py — the full pipeline: analyze → validate → plan → execute → report, plus the five `_stage`/`_stage_optional` NotImplementedError wrappers, EchoSink, and EXIT_NOT_READY
- core/codes.py — E315 appended to the Layer-3 block (correct merge-protocol append)
- Dockerfile.base (yeet/ubuntu:22.04), Makefile `image`/`docker` targets
- 13 test files (test_backend/runner/steps/script/env/state_files/commands/images/docker_backend/local_backend/workspace/paths/platform_)

Verified against project standards — the good
- All session-1 claims reproduce. The exec trap is real: `DockerExec` does the low-level exec_create → exec_start(stream, demux) → exec_inspect dance because `exec_run(stream=True)` returns exit_code=None (docker_backend.py:110–142); the exit-42 test (test_docker_backend.py:96) passes against a live daemon. Full docker suite: 18 passed / 605 deselected in 96s. Fast suite: 170 passed / 18 deselected in 2.9s.
- The five gates were genuinely green at his commit. At current HEAD the repo is red, but every failure is in Dev A/B files (PTH211 in test_analyzer.py, 10 unformatted files in templates/validation/planner) — none of Dev C's. ✓
- Frozen contracts untouched: core/ir.py, core/diagnostics.py, core/result.py — zero diff in both commits. codes.py change is a single appended rule. ✓
- Tier rule held: executor is tier 5, cmd_run tier 7, imports go downward only. ✓
- Risk #11 chokepoint honored: `_emit` in steps.py is the only LogEvent constructor in the package; masking is applied exactly there. ✓
- slug("..") fix is present and correct (workspace.py:52 — `.strip("-.")` → "job" instead of a dir-escape). label() = "Run <first line>" (steps.py:59) matches GitHub's rendering. ✓
- env.py's base_env/GITHUB_* set agrees with Dev B's build_github_context keys (github_env maps the nine promised fields). The container variant hardcodes RUNNER_OS=Linux — right call. ✓
- Interpolate degradation is contained and never silent: DEGRADED_NOTE emitted once per job at the end. ✓
- Exit codes EXIT_OK=0 / EXIT_JOB_FAILED=1 / EXIT_BAD_WORKFLOW=2 / EXIT_NO_DOCKER=3 present; daemon-unreachable → exit 3 confirmed. SIGINT/SIGTERM + atexit reap_all → no stray containers. ✓
- No new dependencies (pyproject.toml untouched — docker>=7.1 was pre-declared). ✓

Deviations / defects I found
1. Stale seams after the fact. Every seam Dev C carved out for others has landed — analyze, validate_file, build_plan, RunConsole.emit (console.py:41 is real), load_secrets — yet cmd_run.py still carries all five `_stage`/`_stage_optional` wrappers, their "owner: Dev X" messages, and EchoSink. The wrappers now only mislead (a real NotImplementedError from a finished module would be reported as "not implemented yet"). EchoSink is dead weight since D6 landed. The docstring says delete the wrapper at your stage's call site; none were.
2. EXIT_NOT_READY=1 collides with EXIT_JOB_FAILED=1 (cli/__init__.py:13) — two names, one value. Since the seams that made EXIT_NOT_READY meaningful are gone, it should be deleted with the wrappers.
3. interpolate.py's two `except NotImplementedError` blocks + `_degraded` were meant to be removed when Dev B lands B4/B6; Dev B has landed evaluate/parse/truthy, so the degradation path is now dead code (still imported, still referenced, but evaluate() raises ExprSyntaxError, not NotImplementedError). Same "delete the seam" instruction unexecuted.
4. env.py's github_env ignores unknown keys (by design) but maps only 8 of the 9 promised fields — the session-context claimed the set "agrees"; the executor's GITHUB_* env and Dev B's github context aren't wired together at all yet (no call site for github_env). Not a bug, but the hand-off isn't actually connected.

Bottom line: the strongest, most honestly-documented session so far — claims match code, tests, and live Docker behavior; the exec trap, masking chokepoint, cleanup handlers, and slug fix are exactly as described, and frozen-contract/tier/gate discipline is clean. The only real smell is that every "delete me when X lands" seam is still in place after X landed, which is exactly what those comments were meant to prevent. Highest-leverage cleanups: (1) strip the four wrappers + EchoSink from cmd_run.py and delete EXIT_NOT_READY, (3) drop interpolate's dead degradation path now that Dev B's evaluator is real.


# session-2 work


Here's my full verification of DEV-D's session-2 work (commits 3ddacc9 + b21bf08, 41 files, ~2,330 lines).
What changed
Area	Delivered
reporting/	theme.py (status vocab + colors + NO_COLOR/TTY), render.py (code-frame renderer), console.py (RunConsole LogSink), json_out.py, sarif.py
validation/	layer0_file.py (E001–E007), pipeline.py (validate_file), layer4_lint/ base runner + 5 rule modules (W401–W415)
core/	codes.py (full registry, 55 rules), config.py (platformdirs + lint.yml), one-line fix to masking.py
secrets/storage/triggers	store.py, runs.py, artifacts.py, cache.py, watcher.py, hooks.py
cli/	cmd_check, cmd_explain, cmd_secrets, cmd_logs, cmd_watch, cmd_hooks wired (todo() removed)
docs/tests	rules.md (generated), gen_rules_doc.py, ADRs 0002–0006, 5 test files (54 tests)
Verified against project standards — the good
- All 5 CI gates genuinely green (I ran them): ruff, ruff format --check, mypy strict on 98 files, import-linter (2 kept, 0 broken), 192 passed, 18 deselected.
- Frozen contracts untouched: core/ir.py, core/diagnostics.py, core/result.py — zero diff. ✓
- Tier rule held: no layer violations introduced; secrets//storage/ correctly at tier 5, CLI at 7. ✓
- §4 contract signatures mostly kept: validate_file, render_diagnostics, to_json, to_sarif, RunConsole(LogSink), run_lints, load_lint_config, load_secrets. ✓
- codes.py append-only within layer blocks (merge protocol §8) — seed rows preserved; rules.md regenerates from codes.py so it can't drift. ✓
- Risk #20 handled: renderer clamps indices + try/except fallback, tested with an absurd Position(9999, -50). ✓
- Masker fix is correct (4-char floor now applied before base64 variants) with a passing test. ✓
- No new dependencies added (pyproject.toml untouched — no §8 announcement needed). ✓
Deviations / defects I found
1. Layer-4 lints never fire in production — a real integration bug. Rules self-register at import time, but nothing imports the rule modules (only base.py is imported). Verified: RULES is empty at runtime. Tests pass only because test_lint.py imports the rule classes directly, masking the gap.
2. yeet check currently does nothing end-to-end. Layers 1–3 (layer1_yaml, layer2_schema, layer3_semantic) are still stubs; pipeline.py catches NotImplementedError and returns early. Verified: a clean workflow file → zero diagnostics, no Workflow built. This is the sanctioned red state (waiting on Dev A/B), but session-context's "Wired yeet check to 5-layer pipeline" overstates it.
3. Secrets are stored in plaintext JSON — direct violation of D21/architecture §5, which explicitly requires Fernet encryption with an scrypt-derived key plus an OS keyring layer. The declared cryptography dep is unused; precedence is flag > file > .env (no keyring).
4. Diagnostic-code semantics drift from the design doc. Dev D re-assigned meanings: E206/E208 swapped from §3.10, E303→"matrix config" (doc: duplicate step id), E305–E308/E312–E314 differ, and E317 (doc: missing-secret, error) became W317 "deprecated syntax" while "missing secret" moved to E307. Dev B implementing B9 against plan.md will hit codes with different meanings than the doc promises — needs a standup alignment.
5. Two minor logic issues: run_lints docstring claims a lint.yml-promoted error "still only blocks under --strict", but DiagnosticBag.exit_code() returns 2 on any error, so it blocks unconditionally; and pipeline.py swallows real exceptions with except (NotImplementedError, Exception) — silent failure, against the "never silently degrade" ethos in Dev C's interpolate.
6. Triggers deviate from plan: watcher is a polling rglob loop, not the watchdog observer with a per-project lock (D26); signatures watch_directory/install_hooks vs the §4 contract watch/install. And print("Watcher error: ...") is exactly the direct-error-print risk #2's CI grep is meant to catch.
Bottom line: solid, idiomatic work that respects the frozen contracts, tiers, and gate discipline — but it stops short of its own claims in three places that matter: the lint layer isn't reachable, secrets aren't encrypted, and the code registry silently redefined the Layer-3 contract.
Want me to fix any of these? The highest-leverage ones: (1) import the five rule modules so lints actually run, (3) encrypt the secret store, and (5) correct the strict/override behavior.


# session-3 work


My verification of DEV-A's session-3 work (commits b44947d + e58d138; analyzer/, parser/, actions/, templates/, cli/ — ~24 files).

What changed
Area	Delivered
analyzer/	root.py (walk-up root find, no git shell-outs), markers.py (16 file + 2 extension markers, all filled), discover.py (depth/inode/permission-safe walk, precedence .yeet/flows > .github/workflows > root yeet.yml, foreign CI reported separately), fingerprint.py (engines.node / requires-python version pinning), project.py (analyze() = A3→A5→A6)
cli/	app.py gained --no-color + NO_COLOR env (A8); cmd_scan.py the full §3.9 report (A9) — verified live, works end-to-end
parser/	loader.py (A10: ruamel rt, E101/E102/E103/E104/W105, on:→True key rename that preserves lc.data), aliases.py + aliases.yml (A11: one-line-each table, recursive in-place rewrite, never fails), schema/workflow.schema.json (A12), builder.py (A16: dict→IR with lc.value/key positions, E204/E205, scalar needs→list)
validation/	layer1_yaml.py (A14 wrapper), layer2_schema.py (A13: jsonschema + best_match, E201 w/ A15 did-you-mean, E202/E203/E206/E207/E208), suggest.py (A15)
actions/	resolver.py + composite.py (A17/A20: local composite, INPUT_* env + defaults, E313/E314/W319; remote owner/repo@ref shallow-clone cache keyed by ref, GitClone test double)
templates/ + cmd_init.py	Jinja2 StrictUndefined templates, init --auto from fingerprint, bundled .yeet/actions/checkout action (A19), .gitignore block
tests/fixtures	9 valid golden (01–09 incl. composite expansion) + 14 invalid (E101–E104, E201–E208, W105)

Verified against project standards — the good
- Gates at HEAD — CORRECTED during the session-4 review: the gate runs here were made during a degraded tool window and their "all green" result was unreliable. Re-verified against the same commit (25ff733, clean working tree): ruff check FAILS (PTH211 at tests/unit/test_analyzer.py:164), ruff format --check FAILS on 10 files (3 of Dev A's: templates/workflows.py, validation/layer2_schema.py, tests/unit/test_templates.py), mypy strict clean on 101 files, import-linter 2 kept 0 broken, pytest 605 passed / 18 deselected. So Dev A's code itself is green on mypy/import-linter/tests, but the committed tree does NOT pass `make check` — see the session-4 review for the full account.
- Owner/Tier docstrings on every file, tiers respected (analyzer/parser at 2, layer1/2 at 3, CLI/templates at 7); no new dependencies (jsonschema/jinja2/pathspec already declared — pyproject diff is only mypy ignores).
- The pipeline now genuinely builds the IR end-to-end: validate_file(01-minimal-canonical) → [], Workflow(name="canonical minimal", jobs={build}); each invalid fixture fires exactly its own code (verified live for E201/E206/E208).
- Position discipline is real and preserved through the whole chain — rename_key moves lc.data, builder reads lc.value/key as it builds, layer2 maps jsonschema absolute_path back to key positions. Verified: the E208 code-frame points at the exact line.
- `yeet scan` works live: repo → project line + branch + "no flows" → suggests init --auto (exit 0); a dir with an invalid flow shows "✖ 1 errors → run yeet check". The session-3 caveat "per-flow validity prints 'validation not built yet'" is resolved now that Dev B's layer3 landed.
- One-code-per-fixture discipline (tests/invalid/E*.yml) is exactly the plan.md intent; golden .expected.json pairs for 9 fixtures.

Deviations / defects I found
1. codes.py registry drifted again (same class as session-2 finding #4, now Dev A's own codes): the "single source of truth" titles contradict what layer2_schema and resolver actually emit. E206 is registered as "invalid event name" but the implementation (and fixture E206.yml `jobs: {}`) is "no jobs defined"; E208 is "empty step list" but fires for `on: [qwerty]`; E313/E314/W319 titles are swapped against resolver.py (E313 = uses can't be satisfied, E314 = required input missing, W319 = undeclared `with:` input). rules.md is generated from codes.py and `yeet explain` reads it, so users get told the wrong thing.
2. Layer-4 lints are still dead at runtime (my session-2 finding, unfixed — not Dev A's file but now load-bearing): RULES is empty because nothing imports the five rule modules. Verified twice, plus `yeet check` on `actions/checkout@main` (a W402) prints nothing and exits 0. So "check on init output is clean" is only vacuously true today.
3. Two dead/loose seams left behind now that layers are real: cmd_scan._flow_validity still has an except NotImplementedError → "validation not built yet" branch (unreachable), and pipeline.py's redundant `except (NotImplementedError, Exception)` around build_workflow silently swallows real build errors (session-2 finding #5, still open).

Bottom line: the strongest session so far — Dev A's code is idiomatic, tier-clean, position-faithful, and the parser/analyzer/actions seams it handed off are all real and verified. It adheres to the standards. Two things I'd fix: regenerate/correct codes.py titles so rules.md and `yeet explain` match reality, and wire the five rule-module imports so the lint layer finally fires.




# session-4 work


My verification of DEV-B's session-4 work (commits a11da0f + 25ff733; expressions/, planner/, core/graph.py, validation/layer3_semantic.py, cli/cmd_graph.py, docs/adr/0007).

What changed
Area	Delivered
expressions/	lexer.py (byte-offset tokenizer, 48 tests), ast_nodes.py (9 node types + ExprSyntaxError(offset,msg)), parser.py (Pratt parser, GitHub precedence: [] . * ( > ! > comparisons > ==/!= > && > ||, never partial trees), contexts.py (10 contexts + build_github_context reading .git via stdlib, no git binary, worktree-aware, graceful non-git degrade), evaluator.py (GitHub loose equality + truthy set, member/index/splat, missing key -> null), functions.py (12 builtins, hashFiles sorts+dedups paths, SHA-256 over path+content+size), _comparison.py
core/	graph.py — find_cycle (three-colour DFS, returns the path) + topo_waves (in-degree waves), deliberately IR-free and tier 0 so BOTH validation (E302) and planner share one cycle walk
validation/	layer3_semantic.py — E301/E302/E303/E309/E310/E311/E312 (21 tests); uses core.graph.find_cycle, positions from key_pos; remaining L3 codes left to other owners, noted in docstring
planner/	matrix.py (product -> exclude -> include, GitHub's real order — documented deviation from plan; 11 tests), plan.py (build_plan: matrix expansion -> instance DAG -> topo waves; stable leg keys "build (node 16)"; 13 tests)
cli/	cmd_graph.py — render_plan() pure ASCII wave tree + own discovery; 6 tests
executor/runner.py	B13 skip/fail-fast semantics (Dev C tier-5 file; 3 fail-fast tests) — location deviation documented in the module docstring
docs/	ADR 0007 (tier-rule consequences: core/masking, core/events, actions->tier 2, core/graph)

Verified against project standards — the good
- Dev B's own suite: 260 tests pass; per-file counts match the claims exactly (lexer 48, matrix 11, plan 13, cmd_graph 6, layer3 21).
- Behavior verified live, not asserted: matrix exclude removes the {windows,18} leg and include appends {macos,20} as a new leg; topo_waves on a diamond -> [[a],[b,c],[d]]; find_cycle returns the path a->b->c->a; lexer offsets are byte-accurate; layer3 fires E301+E311 on a crafted workflow; `yeet graph` on a matrix workflow prints 5 instances in 2 waves (exit 0) and refuses an E301 workflow (exit 2).
- Tier rule respected AND documented: the planner/validation sharing problem is solved by putting the algorithm in core.graph (tier 0) rather than breaking the contract — exactly ADR 0007's decision; lint-imports 2 kept, 0 broken at HEAD.
- Codes align with the registry this time: E301/E302/E303/E309–E312 match codes.py titles (contrast with session-3's E206/E208 drift).
- Documented deviations are real deviations with code-level explanations (matrix order, if: at runtime, B13 in runner.py) — that is the standard, not a violation.
- No git subprocess anywhere (contexts reads .git files directly); hashFiles is order-independent by construction; every file has Owner/Tier docstrings.

Defects / deviations from the written claims
1. "Status: complete and green" is FALSE for the committed tree — the gate is red at HEAD (25ff733, clean working tree, verified twice): `make check` fails on `ruff check` (PTH211: os.symlink should be Path.symlink_to at tests/unit/test_analyzer.py:164, a Dev A test) and `ruff format --check` fails on 10 files, 7 of which are Dev B's (core/graph.py, planner/matrix.py, planner/plan.py, test_cmd_graph.py, test_evaluator.py, test_layer3.py, test_lexer.py). The drift is cosmetic (one-line list comprehensions ruff wants reflowed — a 30-second `make fix`) but CI would fail on the first push. mypy (101 files), import-linter, and pytest (605 passed / 18 deselected) are green.
2. The stated "511 passed, 18 skipped" figure doesn't match HEAD: it's 605 passed / 18 deselected today. Not a violation — worth noting the numbers in the context doc and the actual commit diverged.
3. Dead seam: cmd_graph's "parser is not ready (Dev A)" fallback branch is unreachable now that build_workflow is real (verified: it renders fine end-to-end). Harmless, but it duplicates analyzer discovery (documented as intentional at the time).
4. Carried-over, still open (not Dev B's): the L4 lint rules never register at runtime (RULES empty), pipeline.py's `except (NotImplementedError, Exception)` silently swallows build errors, and codes.py titles for E206/E208/E313/E314/W319 contradict the implementations.

Bottom line: the highest-quality session to date — idiomatic, tier-clean, well-documented deviations, real behavior verified end-to-end, and the CSV/evaluator/graph seams all hold. It adheres to the standards in every dimension except one: the tree was committed without `make fix`, so the exact gate the session claims green is red. That is a one-command fix (`make fix`), not a design issue.



Review appended to undone.md under a new # session-1 work section. Summary:
What DEV-C built (session-1, commits a84b7b0 + 3b76594, 36 files, +4,473 lines): the entire executor — executor/ package (docker_backend, local_backend, runner, steps, script, env, state_files, commands, interpolate, images, workspace, paths, platform_, build) + cli/cmd_run.py wiring + E315 in codes.py + Dockerfile.base + 13 test files.
Standards check — verified against his claims:
- All gates were green at his commit; current HEAD reds are all in Dev A/B files, none his. Frozen contracts (ir.py/diagnostics.py/result.py) zero diff; tier rule held; no new deps.
- Reproduced live: exec trap (exec_create→exec_start→exec_inspect, exit 42 test passes), 18 docker tests passed against a real daemon (96s), 170 fast tests passed (2.9s).
- Slug ..-escape fix, label() = "Run <first line>", masking chokepoint, SIGINT cleanup, exit codes all as documented.
Defects found (all "delete-the-seam" items unexecuted after the seams landed):
1. All five _stage/_stage_optional wrappers + EchoSink still in cmd_run.py even though every stage they guard (analyze, validate_file, build_plan, RunConsole.emit, load_secrets) is now real — the "not implemented yet, owner: Dev X" messages would now mislead.
2. EXIT_NOT_READY=1 collides with EXIT_JOB_FAILED=1 — duplicate name/value.
3. interpolate.py's degradation path is dead code now that Dev B's evaluator exists.

# session-5 work — integration pass

Not a subsystem session. This one connected the four that already existed,
closed every carried-over defect listed above, and added the missing docs.

## Status of every defect previously recorded in this file

| From | Defect | Status |
|---|---|---|
| s1 #1 | `cmd_run`'s five `_stage` wrappers + `EchoSink` outlived their seams | **fixed** — removed |
| s1 #2 | `EXIT_NOT_READY=1` collides with `EXIT_JOB_FAILED=1` | **fixed** — deleted |
| s1 #3 | `interpolate.py`'s degradation path is dead | **fixed** — `except NotImplementedError` gone; `Degradation` kept for the real `contexts=None` case, note reworded |
| s1 #4 | `env.py::github_env` has no call site | **still open** — Dev C/B hand-off, unchanged |
| s2 #1 | Layer-4 lints never fire (`RULES` empty) | **fixed** — package `__init__` imports the five rule modules; 5 regression tests incl. a subprocess check |
| s2 #2 | `yeet check` does nothing end to end | **fixed** — was the missing dialect pass; now clean-exits on the walking skeleton |
| s2 #3 | secrets stored in plaintext JSON | **fixed** — Fernet + scrypt; `keyring` optional, not a new dep |
| s2 #4 | codes.py semantics drift | **fixed** — E206/E208/E313/E314/W319 titles corrected against the implementations |
| s2 #5 | `run_lints` docstring wrong about `--strict`; `pipeline.py` swallows exceptions | **fixed** — docstring corrected; both now report `YEET-E900` |
| s2 #6 | watcher is a polling loop, wrong signatures, `print()` | **fixed** — watchdog + debounce + lock; `watch(paths, on_change)` per §4; 22 tests |
| s3 #1 | codes.py titles contradict layer2/resolver | **fixed** — same as s2 #4 |
| s3 #2 | Layer-4 lints dead at runtime | **fixed** — same as s2 #1 |
| s3 #3 | `cmd_scan` unreachable branch; `pipeline` swallows | **fixed** |
| s4 #1 | tree committed without `make fix`; gate red at HEAD | **fixed** — and `make check` now includes `format`, which is why it drifted |
| s4 #2 | test-count claims diverged from HEAD | n/a — counts in session-5 were run, not quoted |
| s4 #3 | `cmd_graph`'s "parser is not ready" fallback unreachable | **fixed** — removed |
| s4 #4 | carried-over: lints, swallowing, code titles | **fixed** |

## New defects found this session (all fixed)

1. **`aliases.normalize()` had no call site.** The dialect — the project's
   headline feature — failed its own validator with 5 errors on the exact
   workflow in plan.md §6. Four sessions of review missed it because the golden
   tests call `normalize()` by hand, so the unit tests were green throughout.
2. **`RunStore` was never constructed.** `yeet logs` always answered "no run
   logs found"; §3.2's fan-out had only its console half.
3. **W403 fired on `runs-on: ubuntu-latest`** — a runner label, not an image
   tag. Would have fired on almost every real-world workflow, i.e. on the
   compatibility corpus we intend to demo.
4. **The `post-commit` hook shim passed `--sha`, which `yeet run` does not
   accept.** Every commit would have errored; D27 could not have passed.
5. **`hooks install` clobbered pre-existing user hooks** with no check.
6. **CI had never run**: `.github/workflows/` was inside `yeet/`, and GitHub
   only discovers workflows at the repo root. It would also have failed at
   `pip install -e .` (no root `pyproject.toml`).
7. **`RunConsole` emitted the group header before the job header.**
8. **`${{ secrets.X }}` always evaluated to empty.** `Contexts.secrets`
   existed but `cmd_run` never populated it, so secret values reached the
   `Masker` and never the evaluator. A step's `drip: {TOKEN: ${{ secrets.T }}}`
   got an empty string. This is the nastiest of the set, because the symptom
   — no secret in the log — is exactly what success looks like.

## Still open, deliberately

- `env.py::github_env` has no call site (s1 #4) — the executor's `GITHUB_*` env
  and Dev B's `github` context are still not wired to each other.
- Layer-3 codes E304–E308, E313–E317, W318 registered but unimplemented;
  `layer3_semantic.py`'s docstring names them.
- `tests/corpus/` empty — the "% of syntax supported" metric has no inputs.
- C15/C16 (Docker actions, JS actions) remain seams; `steps.py` marks such steps
  SKIPPED rather than pretending they passed.
- `docs/architecture.md` has drifted; `docs/handbook.md` is now the front door.

## Verification

Every claim above was run, not asserted:

    make check       all gates green
    pytest           671 passed, 18 deselected (docker)
    mypy src         101 files, strict, clean
    lint-imports     2 contracts kept, 0 broken

and end to end on a scratch repo, both spellings:
`yeet scan` → `yeet check` (exit 0) → `yeet graph` → `yeet run` (exit 0,
"we are so back") → `yeet logs` (replays it) → `yeet secrets set` (ciphertext on
disk, value absent from the file).





  # DEV-C 
  — fix the context plumbing. Highest value in the repo. Thread a per-instance Contexts through runner.py →
  StepLoopConfig: matrix from inst.leg, needs from upstream JobResults, env layered workflow → job → step over
  os.environ, steps from the step_outputs dict that's already tracked. Then wire github_env at the same call site
  and close a 5-session-old thread. Add an e2e test asserting a matrix leg prints its own value — that's the
  tripwire that would have caught this.

  # DEV-A 
  — decide loot/stash. Either implement (IR fields + schema + builder) or cut them from aliases.yml and the
  handbook. Shipping a documented feature that errors is worse than not having it. Then fill tests/corpus/ with 5–10
  real OSS workflows and turn it into a parametrized "parses without E1xx/E2xx" test — that's your demo metric, and
  it'll find schema holes nothing else will.

  # DEV-B 
  — finish Layer 3. E304–E308, E313–E317, W318, one invalid fixture each. Highest-value: E307 missing-secret
  and E316/E317. This is the layer that makes check look thorough on a stranger's repo.

  # DEV-D
   — commit the work and get CI green. Commit those 41 files today, push, watch the 3-OS matrix actually run,
  fix what Windows breaks (it will — paths and CRLF). Then fix the console double-rendering: in my matrix run, test 
  (node 16) printed its header three times. Cosmetic, but it's the money shot of the demo.

  Everyone: the handbook's rule — when you finish a module, grep for its call site — is the single most valuable
  sentence in your docs, and the matrix bug is the fourth violation of it. Make it a PR checklist item, not a
  paragraph.


# session-6 work — DEV-C, the contexts

The bug the session-5 review named as "the nastiest of the set" — a `Contexts`
field that exists, parses, and is never populated — turned out to have five
more instances of itself. This session fixed the class, not the instance.

## What was broken

`cmd_run._contexts()` built ONE `Contexts` for the whole run and filled three
of its ten fields: `github`, `secrets`, `env=os.environ`. That object was
threaded unchanged through `RunOptions` -> `JobContext` -> `StepLoopConfig` ->
`expand()`. Everything that varies per job instance or per step was therefore
permanently empty:

| Context | Symptom |
|---|---|
| `matrix` | `${{ matrix.node }}` expanded to `""` in **every leg that has ever run** |
| `env` | workflow/job/step `env:` invisible to `${{ env.X }}` |
| `needs` | `needs.build.outputs.*` and `.result` always empty |
| `steps` | `steps.<id>.outputs.*` always empty, so a job's `outputs:` block was too |
| `runner` | `${{ runner.os }}` empty |
| `job` | `${{ job.status }}` empty |

Two more found while fixing it:

- **`Workflow.env` was parsed and dropped on the floor.** `_step_env` layered
  base < exported < job < step and never looked at the workflow block, so a
  variable declared once at the top of a file reached nothing beneath it.
- **`env.py::github_env` still had no call site** (s1 #4, open five sessions):
  `${{ github.sha }}` resolved while `$GITHUB_SHA` did not.

## What was done

- **NEW `src/yeet/executor/contexts.py`** (tier 5). `for_instance()` builds a
  per-job-instance `Contexts` (matrix from `inst.leg`, `needs` from upstream
  `JobResult`s, `job.status`); `for_step()` adds `env`, `runner` and `steps`.
  Every function **returns a new `Contexts` and never mutates its argument** —
  jobs in a wave run in parallel threads off one base object, and sharing a
  mutable one is a race that surfaces as one leg reading another leg's matrix.
- **`runner.py`** — builds the per-instance contexts in `_run_wave`; new
  `RunOptions.workflow_env`; `_job_env()` merges `github_env(contexts.github)`
  into every job's environment; `_align_github_context()` makes
  `${{ github.run_id }}` and the log directory the same string (they were two
  different generated ids, so `yeet logs <id>` could not find a run).
- **`steps.py`** — `_step_contexts()` per step, built BEFORE `if:` is
  evaluated so a condition can see matrix/needs/steps/env. `_step_env` split
  into `_layered_env` (feeds the `env` context) and `_with_state_files` (does
  not — `$GITHUB_ENV` is our scratch file, not the user's variable).
  `build_job_result` now expands `outputs:` against the post-last-step context.
- **`RESULT_WORDS`** — expressions speak GitHub's vocabulary (`success`,
  `failure`, `skipped`, `cancelled`), not the console's (`slayed`, `flopped`).
  Real workflows are full of `if: needs.build.result == 'success'` and we
  promise those files run unchanged. `slayed`/`flopped` stay in `reporting/`.

## Verification

Run, not asserted:

    make check      all six gates green
    pytest          686 passed (was 672: +10 unit, +4 e2e), 18 deselected
    pytest -m docker  18 passed against a live daemon
    mypy src        102 files, strict, clean
    lint-imports    2 contracts kept, 0 broken

Live, on the local backend AND in real containers:
`matrix`, `env` (all three levels), `needs.<job>.result`/`.outputs`,
`steps.<id>.outputs`/`.conclusion`, `runner.os`, `job.status`, and
`${{ github.sha }} == $GITHUB_SHA` all resolve. In a 2-leg matrix each leg
prints its own value, in parallel containers, and `runner.os` reports `Linux`
on a macOS host (it is read from the step's own env, so it cannot disagree
with `$RUNNER_OS`).

**The tripwire was checked by breaking it:** reverting `for_instance` to
return the shared object fails `test_a_matrix_leg_sees_its_own_value` and
`test_needs_carries_result_and_outputs_between_jobs`. A test that cannot fail
is not a tripwire, and the absence of exactly this test is why the bug lived
through four review sessions with a green suite.

## Still open

- `loot:`/`stash:` are in `aliases.yml` and the handbook's dialect table, but
  the canonical schema and IR carry no such keys, so a workflow using them is
  rejected with E201. `storage/artifacts.py` and `cache.py` are written and
  have zero call sites (D25). Either wire them or cut the aliases.
- `actions/docker_action.py` and `js_action.py` are empty files (C15/C16).
- Layer-3 codes E304-E308, E313-E317, W318 registered but unimplemented.
- `tests/corpus/` still empty.
- CI has still never run: `.github/workflows/ci.yml` is staged at the repo root
  but uncommitted.
- `RunConsole` re-emits a job header per event group — a matrix job prints its
  header several times.

## session-6b — the first CI run, and what it caught

CI ran for the first time in the project's life (commit 7924947). Result:
`ubuntu-latest` x2, `macos-latest` x2, `docker` and `rules-doc` all green;
**windows-latest red on both 3.11 and 3.12.** Two distinct causes, both fixed.

### 1. `script_suffix` did not apply the platform default — a real product bug

`shell_argv(None, ..., in_container=False)` resolves to `pwsh` on Windows.
`script_suffix(None)` resolved separately and always fell through to `.sh`. So
every step without an explicit `shell:` was written to `script.sh` and invoked
as `pwsh -NoProfile -NonInteractive -File ...script.sh` — and pwsh runs `.ps1`
and nothing else, which the note on `script_suffix` had said all along.

Every job on Windows flopped. `yeet run` exited 1 where the test expected 0.

Fixed by extracting `script.resolve_shell(shell, *, in_container)` and having
BOTH functions call it. `in_container` is now a required keyword on
`script_suffix` rather than defaulted: the answer differs between the two
backends on one machine, and a default would let the bug back in silently.

The shape of this bug is worth naming: **two functions deriving the same
default independently.** The existing test asserted `shell_argv` picked `pwsh`
on Windows and never asked what suffix went with it, so it passed throughout.

### 2. The e2e harness decoded child output with the wrong codec

`subprocess.run(..., text=True)` without `encoding=` decodes with the locale
encoding — cp1252 on Windows. `PYTHONIOENCODING=utf-8` configures the CHILD
only, so the child emitted UTF-8 (`●`, `├─`, `📦`) and the parent read cp1252:
`UnicodeDecodeError` inside subprocess's reader thread, `stdout` came back
None, and four tests died on `result.stdout + result.stderr` with a TypeError
naming neither the encoding nor the platform. Now `encoding="utf-8",
errors="replace"`.

### 3. e2e steps that are bash-specific now say so

`${#VAR}`, `>> "$GITHUB_OUTPUT"` and `$VAR` are POSIX; on Windows the local
default is correctly `pwsh` (GitHub's default there too, and plan.md C13's).
Those steps now carry `shell: bash`, which is what a real cross-platform
workflow does and which exercises C13's "honors `shell:`" as a bonus. The
walking skeleton and the matrix tripwire deliberately keep the default shell,
so they still exercise the pwsh path on Windows — they are what catches a
regression of #1 end to end.

### Verification

    make check        all six gates green
    pytest            690 passed, 18 deselected
    pytest -m docker  18 passed against a live daemon

Both new tests were checked by breaking them: restoring the old
`script_suffix` fails `test_the_suffix_matches_the_shell_that_will_run_it` and
`test_on_windows_the_script_is_written_where_pwsh_can_run_it`.

Windows itself is verified by CI on the PR, not locally — macOS cannot prove it.

## DEV-C status

C's assigned work is complete: contexts (s6), plus the Windows shell pair.
Remaining C items are C15/C16 — `actions/docker_action.py` and `js_action.py`
are still empty files — and the executor half of `loot:`/`stash:`, which is
blocked on Dev A adding the IR fields and schema keys first.

## session-6c — three-OS CI is green

`shell: bash` on Windows reached `C:\Windows\System32\bash.exe`, which is the
WSL launcher rather than a shell; with no distribution installed it fails with
a message about Linux distributions. `platform_.shell_executable()` now
resolves bash/sh to Git for Windows. No-op elsewhere and inside containers.

With that fixed, all 660 Windows tests PASSED and the step still exited 1: the
session died with a KeyboardInterrupt during `test_watcher.py`. Cause:
`ProjectLock` asked `os.kill(pid, 0)` whether a lock holder was alive. On
Windows CPython special-cases only CTRL_C_EVENT and CTRL_BREAK_EVENT and
otherwise calls `TerminateProcess`, so signal 0 **kills** the target. The lock
test writes `os.getppid()` as a stand-in live holder, so probing it terminated
the pwsh process running the CI step. **Not only a test bug** — a stale
`watch.lock` with a recycled pid would have killed an unrelated program on a
user's machine. `platform_.pid_alive()` now owns it: `OpenProcess` +
`GetExitCodeProcess` on Windows, `os.kill(pid, 0)` elsewhere.

Then mypy: `ctypes.windll` needs `# type: ignore[attr-defined]` off Windows,
and `warn_unused_ignores` rejects that same ignore ON Windows. No spelling with
an ignore is green on all three; `getattr(ctypes, "windll")` needs none.

Smaller items in the same pass: `script_suffix` gained a required
`in_container` keyword (see 6b); `script.py` calls `platform_.is_windows()`
through the module so the platform decision has ONE patch point (tests had been
patching `script.is_windows` while `shell_executable` read
`platform_.is_windows`); e2e fixtures are written `newline="\n"` so the same
fixture is the same bytes on every OS.

### Result

    CI run 31628874225 — all 8 jobs green, the first time in the project's life

    check (ubuntu-latest, 3.11)   check (ubuntu-latest, 3.12)
    check (macos-latest, 3.11)    check (macos-latest, 3.12)
    check (windows-latest, 3.11)  check (windows-latest, 3.12)
    docker                        rules-doc

695 tests locally, 18 container tests against a live daemon.

The lesson worth keeping: **every Windows bug in this sequence was a function
that behaves differently there and was called as if it did not** — `os.kill`
probes on POSIX and kills on Windows; `bash` is a shell on POSIX and a WSL
launcher on Windows; `text=True` decodes UTF-8 on POSIX and cp1252 on Windows;
`write_text` writes LF on POSIX and CRLF on Windows. Four instances of one
shape, and CI found all four in a single afternoon after never having run.




---
***
---

# session-1.1

Answering your question directly

  Yes — macOS and Linux run fine, and now Windows does too. All eight CI jobs pass:

  ✓ check (ubuntu-latest, 3.11)    ✓ check (ubuntu-latest, 3.12)
  ✓ check (macos-latest, 3.11)     ✓ check (macos-latest, 3.12)
  ✓ check (windows-latest, 3.11)   ✓ check (windows-latest, 3.12)
  ✓ docker                         ✓ rules-doc

  That's the first fully green CI run in the project's life. The macOS and Linux legs were never in danger —
  shell_executable is a no-op off Windows by construction, and container steps skip it entirely — but I verified
  rather than assumed: 695 tests + 18 container tests locally on macOS, a live matrix run, and both ubuntu legs
  green on every push.

  What it took — four rounds, each uncovering the next layer

  Your instinct to ask was right, because the Windows work kept finding real product bugs, not test noise:

  1. script_suffix ignored the platform default. shell_argv resolved to pwsh on Windows; script_suffix always fell
  through to .sh. So every step was written to script.sh and handed to pwsh -File, which takes .ps1 only — the
  function's own docstring said so. Every job on Windows flopped.
  2. bash on Windows is not bash. Bare bash resolves to C:\Windows\System32\bash.exe — the WSL launcher. With no
  distro installed it fails with a message about Linux distributions. platform_.shell_executable() now finds Git for
  Windows.
  3. Probing a pid killed it. With the shells fixed, all 660 Windows tests passed and the step still exited 1 — a
  KeyboardInterrupt during test_watcher.py. ProjectLock used os.kill(pid, 0); on Windows CPython special-cases only
  CTRL_C/CTRL_BREAK and otherwise calls TerminateProcess, so signal 0 kills. The lock test writes os.getppid(), so
  probing it terminated the CI shell. This was never just a test bug — a stale watch.lock with a recycled pid would
  have killed an unrelated program on a user's machine.
  4. mypy couldn't be green on all three at once. ctypes.windll needs # type: ignore[attr-defined] off Windows, and
  warn_unused_ignores rejects that same ignore on Windows. getattr(ctypes, "windll") needs none.

  Every one of those is the same shape: a function that behaves differently on Windows, called as if it didn't. Same
  for the two harness bugs (text=True decoding cp1252, write_text emitting CRLF). CI found all six in one afternoon
  after never having run once.

  DEV-C status: complete

  Contexts (matrix/env/needs/steps/runner/job), github_env wired after five sessions, Workflow.env no longer
  dropped, run-id alignment, GitHub's result vocabulary in expressions, and the Windows cross-platform layer — which
  is explicitly C's ownership per plan.md.

  PR #1 is open, green, and mergeable: https://github.com/TamizhSK/GIST/pull/1

  One thing to flag honestly: fix #3 is in triggers/watcher.py, which is DEV-D's file. I changed one line there to
  delegate to platform_.pid_alive(), because platform_.py's own docstring claims every sys.platform branch. Worth a
  word with D rather than a silent handover.

  Remaining C items: C15/C16 (docker_action.py and js_action.py are still empty files), and the executor half of
  loot:/stash:, which is blocked on DEV-A adding the IR fields and schema keys first.

# session-7 work — the unreachable-module class, again

## The pattern this session kept finding

Six times now a module has been written, unit-tested, reviewed, and never
called. The handbook already names the rule (§6: when you finish a module, grep
for its call site) and it has been broken once per session since it was
written:

| # | Module | Found in | Symptom while broken |
|---|---|---|---|
| 1 | `aliases.normalize()` | s5 | the dialect failed its own validator |
| 2 | `RunStore` | s5 | `yeet logs` never found a run |
| 3 | L4 lint rules | s2/s5 | `RULES` empty, `yeet check` printed nothing |
| 4 | `Contexts` fields | s6 | `${{ matrix.x }}` empty in every leg |
| 5 | `actions/resolver` | **s7** | every `uses:` step SKIPPED |
| 6 | `storage/artifacts`, `storage/cache` | **s7** | `uses: actions/cache` did nothing |

In every case the unit tests were green throughout, because a test that calls
the module directly cannot notice that nothing else does. #5 and #6 are the
same shape as #1: the test performed the step the product had forgotten.

`tests/unit/test_invalid_fixtures.py` was itself an instance — it composed
loader -> aliases -> layer2 -> builder by hand. It drives `validate_file` now.

## Defects fixed that were only reachable once the code was

Both storage modules were wrong in ways nothing could have caught while they
had no callers:

1. **restore-keys did no prefix matching** — the entire point of the feature.
   It hashed each restore key and looked for that exact hash; hashing destroys
   prefixes, so a restore key only ever hit when it exactly equalled the key
   that saved the entry.
2. **`arcname=p.name` flattened cached paths** — `src/dist` and `web/dist` both
   became `dist`, and restoring either wrote over the workspace root.
3. **`extractall` without `filter="data"`** — path traversal out of the
   destination. A cache tarball is attacker-controlled the moment a cache
   directory is shared.
4. **`path: dist/**` stored nothing** — a trailing `**` matches directories
   only in Python's glob, and that is the most common upload-artifact line in
   existence.

## Bugs the real-world corpus found

The corpus earned its keep twice in one session:

1. **E305 was wrong for about ten minutes.** Shipped as the POSIX
   shell-identifier rule; running it over `tests/corpus/` fired 14 times on
   curl's workflow. `env: {cache-name: ...}` read back as
   `${{ env.cache-name }}` is the example in GitHub's OWN caching docs — the
   `env` context is a map lookup, not a shell export. Narrowed to names that
   cannot work anywhere (empty, whitespace, `=`).
2. **E303 rejected an include-only matrix**, and `planner/matrix.py` had the
   same blind spot with teeth: `expand()` returned early on an empty `matrix`
   before it ever looked at `include`, so those legs collapsed into ONE
   unparameterised job. Flask's nine Python versions planned as a single leg
   that tested whatever `python` was on the runner — and reported success.
   Three of the nine corpus workflows use this shape.

Corpus went from 6/9 to 9/9 validating with zero errors.

## Still open

- **C15/C16** — `actions/docker_action.py` and `js_action.py` are still empty.
  A `uses:` pointing at one is now skipped with a message naming the kind and
  the reason, rather than naming a developer, but they do not run.
- **Remote actions** (`owner/repo@ref`) resolve through A20's shallow clone
  only if the action is composite; `actions/checkout@v4` is a node action and
  is therefore skipped. In practice the three built-ins plus local composites
  cover most of what a local run needs, but `checkout` being a no-op deserves a
  word in the docs — the workspace is already the repo, so it is harmless here.
- **W317** ("deprecated workflow syntax") is registered and unimplemented — the
  last one in the Layer 3 block.
- **Built-ins run on the host, not in the job's container.** Deliberate and
  documented: the workspace is a bind mount, so the host sees the bytes the
  container just wrote. It would matter for an artifact path that only exists
  inside the image.
- **`yeet prune --all`** is the only way to reach another project's images now
  that pruning is project-scoped. That is the right default but it means an old
  `yeet-local/<name>:<hash>` tagged before this session (no path hash) is only
  removable with `--all`.
- **The runner's terminal UI** is another developer's thread; `reporting/` was
  left untouched this session on purpose, including the known duplicate
  job-header on matrix legs.

## Verification

    make check        787 passed, all six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py

Every claim above was run. The two matrix/E303 fixes were checked by breaking
them: reverting `expand()` fails
`test_an_include_only_matrix_gives_one_leg_per_entry`, and the concurrency lock
has a five-thread test that fails without it.
