# session-1

C2–C14 + C17 complete. ~2,400 lines of executor, 185 tests (167 fast + 18 Docker).

All five CI gates green: ruff check · ruff format --check · lint-imports 2 kept, 0 broken · mypy strict, 98 files · pytest -m "not docker" 167 passed.

Verified for real, not asserted

With Docker running (17 tests, 90s) — the Day-2 ship target demonstrated: three steps in one container; $GITHUB_ENV written in step 1 read in step 2; a planted secret and its base64 form redacted; ::group::/::add-mask:: round-tripping; stdout/stderr kept apart via demux; the bind mount writable both ways. Then separately:

- make image built yeet/ubuntu:22.04; a job running git --version && curl && jq && node passes — C4's whole reason for existing.
- SIGINT mid-sleep 60 → registry empty, zero surviving yeet- containers (risk #9).
- Daemon unreachable → exit 3 with "Is Docker Desktop running?" (risk #6/C5).
- yeet run in a bare repo → analyzer.project.analyze … owner: Dev A (A7), exit 1, no traceback — the sanctioned red state.

Three things worth your attention

The exec_run trap was real. container.exec_run(stream=True) returns exit_code=None — streaming and the status code are mutually exclusive in the high-level SDK. A naive implementation reports every step as passing. test_a_failing_step_reports_its_real_exit_code asserts exit_code == 42 against a live container; it only passes because of the low-level exec_create/exec_start/exec_inspect path.

Two defects the tests caught in my own code, both fixed at source rather than in the assertion:
- slug("..") produced a directory name that escapes the run directory. Job keys are user-authored YAML.
- Step log labels used Step.display_name, which falls back to the entire run: body — so a multi-line script became a multi-line group header, and every line after the first was emitted before the Masker had seen anything. steps.py::label() now does Run <first line>, as GitHub does.

Two items for standup, not decisions I made unilaterally:
- architecture.md:268 passes environment=base_env and never defines it — nothing in the repo lists the GITHUB_*/RUNNER_* vars to inject. executor/env.py defines it; it needs to agree with Dev B's contexts.py or ${{ github.sha }} and $GITHUB_SHA will disagree inside one step.
- E315 is documented as Layer 3, but resolution needs the image table (tier 5) and validation is tier 3. It now fires at run time, before any container is created — the gate holds, one step later than the doc implies. Noted in images.py and in the appended codes.py row.

I added four files to plan.md's list, all inside executor/: steps.py (shared loop + the single masking chokepoint), runner.py (wave scheduling — plan.md B13 already called it "Dev C's runner loop"), env.py, interpolate.py. Each carries a WHY THIS FILE EXISTS docstring.

cmd_run is wiring only. Its five try/except NotImplementedError blocks are individually marked delete-when-you-implement-your-stage; interpolate.py degrades visibly (one warning per run) rather than silently passing ${{ }} through unnoticed. C15/C16 are left as seams — they need Dev A's resolver, and faking it would have been the wrong kind of progress.






 No API keys, no tokens, no registry credentials, no .env. The executor is a local runner — it talks to a Docker socket on your machine and to nothing else. I also added zero new dependencies (pyproject.toml is untouched; everything is stdlib plus the docker SDK that was already declared), so there's no §8 "announce before adding a dep" item either.

Here's what actually is outstanding.

1. Two commands on your machine — 30 seconds, and one is a risk-register item

git config core.autocrlf input     # currently UNSET
cd yeet && pre-commit install      # currently not installed

Both are plan.md §2.5, still open. core.autocrlf is risk #5. My write_step_script already forces LF unconditionally so a container can't break, but without this setting git will still rewrite .sh fixtures and templates on checkout — and that bites Dev A's templates and Dev D's hook shims, not me. It's the cheapest item on the whole board.

2. Three decisions that are yours, not mine

┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────────┐
│                                                                                                                                  │ Why it   │
│                                                             Decision                                                             │  needs   │
│                                                                                                                                  │   you    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────┤
│ Does Dockerfile.base get published? architecture.md §3.5 says "build your own base image and push to Docker Hub / a local        │          │
│ registry". I built it locally only. Publishing means an org name and a registry login — the one place credentials would ever     │          │
│ enter this project. My default: don't publish, keep make image as a one-time local build. It's ~8s on this machine and removes a │          │
│  whole class of demo-day failure.                                                                                                │          │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────┤
│ Should CI gain a Docker job? ci.yml currently runs only pytest -m "not docker" — the 18 container tests never run in CI, so a    │          │
│ regression in docker_backend.py lands green. Adding a ubuntu-latest-only job that runs make image && pytest -m docker costs ~2   │          │
│ min per push.                                                                                                                    │          │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────────┤
│ The base_env contract with Dev B. executor/env.py defines the GITHUB_*/RUNNER_* set because nothing in the repo did. It has to   │          │
│ match expressions/contexts.py or ${{ github.sha }} and $GITHUB_SHA disagree inside one step. This is a five-minute conversation, │          │
│  not a code change.                                                                                                              │          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────────┘

Say the word on either of the first two and I'll implement them.

3. What's still not done, and who it's waiting on

Mine, blocked:
- C15 / C16 (Docker actions, JS actions) need actions.resolver — Dev A's A17. The seam is in place: steps.py sees a uses: step, reports needs actions.resolver (Dev A, A17) and marks it SKIPPED rather than pretending it passed. Nothing to do until A17 lands.

Mine, deletions pending someone else's work — each is marked in-file so nobody has to hunt:
- interpolate.py — two except NotImplementedError blocks and Degradation, deleted when Dev B ships B4/B6.
- cmd_run.py — five _stage(...) wrappers, one per owner, deleted as each lands.
- cmd_run.py::EchoSink — a temporary plain-text sink, deleted when Dev D ships D6's RunConsole.

Not mine — yeet run stays red until these five land, which is exactly what plan.md §6 sanctions:

┌───────────────────┬──────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│       Stage       │  Owner   │                                                     File                                                     │
├───────────────────┼──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ analyze()         │ Dev A    │ analyzer/project.py                                                                                          │
│                   │ (A7)     │                                                                                                              │
├───────────────────┼──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ validate_file()   │ Dev D    │ validation/pipeline.py                                                                                       │
│                   │ (D8)     │                                                                                                              │
├───────────────────┼──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ build_plan()      │ Dev B    │ planner/plan.py                                                                                              │
│                   │ (B11)    │                                                                                                              │
├───────────────────┼──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ RunConsole.emit() │ Dev D    │ reporting/console.py                                                                                         │
│                   │ (D6)     │                                                                                                              │
├───────────────────┼──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ load_secrets()    │ Dev D    │ secrets/store.py — note this file is completely empty, the function doesn't exist at all, which is why       │
│                   │ (D21)    │ cmd_run reaches it via getattr rather than an import that would crash at module load                         │
└───────────────────┴──────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

The executor itself doesn't need any of them: core/ir.py and planner/plan.py's dataclasses are real, so tests/unit/ builds Workflow/Job/Step/JobInstance by hand and drives a live container end to end. That independence holds today and will keep holding.

One correction to something in your summary: yeet run in a bare repo exits 1, not the sanctioned-red failure — it's EXIT_NOT_READY, deliberately not EXIT_JOB_FAILED (nothing ran) and not EXIT_BAD_WORKFLOW (the file may be fine). That distinction matters if anyone wires the exit code into a hook before the pipeline is complete.







# session-3 

Here's the per-item context for Dev A's plan, A3–A20:
A3 — analyzer/root.py: Walk up from the start dir for .git/ → .yeet/ → .github/workflows/ → ecosystem marker; highest priority wins; stops at FS root or $HOME; never shells out to git. ✓ Implemented. Tests added this session: git repo, bare dir, nested subdir, $HOME boundary (incl. a marker found from below home).
A4 — analyzer/markers.py: Marker→ecosystem→image→default-commands table. Now 16 file markers + 2 extension markers (.csproj/.sln), all filled, no # ... left. ✓ + a table-completeness test.
A5 — analyzer/discover.py: Walk down with EXCLUDE_DIRS, MAX_DEPTH=5, MAX_FILES=20_000, no symlink follow, inode visited-set, per-dir PermissionError handling, .gitignore/.yeetignore via pathspec. Returns flows in precedence order .yeet/flows/ > .github/workflows/ > root yeet.yml, plus foreign CI (.gitlab-ci.yml/Jenkinsfile) reported separately. ✓ Tests added: monorepo w/ node_modules, precedence, foreign CI, depth+ignore, unreadable dir (monkeypatched os.scandir), truncation flag, symlink loop (skips on Windows without symlink privilege).
A6 — analyzer/fingerprint.py: Marker → Ecosystem; reads engines.node from package.json and requires-python from pyproject.toml to pin the version instead of guessing. Dockerfile/compose are infra, not ecosystems. ✓ Tests added: Node (node:18), Python (python:3.11), polyglot, infra exclusion.
A7 — analyzer/project.py: analyze() = A3→A5→A6 + is_git, branch (read from .git/HEAD, never shells out), dockerfile. No YAML parsed here. ✓ Tests added: populated Project (git+branch+flows+foreign+ecosystem+dockerfile) and a bare no-git project.
A8 — cli/app.py: Global --no-color option + honors NO_COLOR env. ✓ Wired in the callback, consumed via _color_enabled in scan. Verified live with yeet --no-color scan and NO_COLOR=1. No CLI harness, so it's hand-verified only.
A9 — cli/cmd_scan.py: The §3.9 report: project line, git/branch, stack, markers, flows with per-flow validity (validate_file upto=2), Dockerfile hint. Zero flows → suggest init --auto, exit 0. ✓ Works end-to-end (smoke-tested on this workspace — root detection correctly climbed to the parent git root). Caveat: per-flow validity prints "validation not built yet" because Dev D's pipeline.validate_file is still a stub; the "3 real repos" target was smoke-tested manually.
A10 — parser/loader.py: ruamel.yaml typ="rt"; E101 syntax (problem_mark), E102 duplicate keys (constructor subclass that raises), E103 non-mapping root, E104 multi-doc, W105 on:→True trap (renames the key, warns). ✓ Gap closed this session: the required tests/invalid/E101.yml…W105.yml fixtures didn't exist — created all 5 + a parametrized test asserting each fires only its code.
A11 — parser/aliases.py: Load aliases.yml once, recursive key rewrite, returns (tree, used_dialect); never fails/warns. manual→workflow_dispatch is handled in the builder, not here. ✓ Covered by golden test 01 (canonical passes through unchanged) and 02 (dialect file rewrites).
A12 — parser/schema/workflow.schema.json: JSON Schema for canonical form only (aliases normalized away). ✓ Present; exercised through layer2 + all golden fixtures.
A13 — validation/layer2_schema.py: jsonschema + best_match, absolute path → jobs.build.steps[2].run; E201 unknown key (with A15 suggestion), E202 missing required, E203 wrong type, E206 empty jobs, E207 invalid id, E208 unsupported event. ✓ Gap closed this session: tests/invalid/E201…E208.yml (8 fixtures, each verified to emit exactly its own code) + the same parametrized test.
A14 — validation/layer1_yaml.py: Thin wrapper over A10 for the pipeline's layer interface. ✓ Present.
A15 — validation/suggest.py: difflib.get_close_matches against canonical keys and aliases. ✓ Implemented and exercised via E201/E208 did-you-mean help text; no dedicated unit test (minor).
A16 — parser/builder.py: dict tree → IR; every Step(pos=...) from lc.value(key), key_pos populated, E204 (both run+uses) / E205 (neither), scalar needs: build → list. ✓ Golden tests exist; gap partially closed: corpus grew 6→9 (added defaults/step-options, multi-job needs DAG, composite use) — still short of the ~20 target, but every IR field is now covered.
A17 — actions/resolver.py + composite.py: local composite (./.yeet/actions/foo/action.yml, runs.using: composite), with: → INPUT_*, defaults, E313/E314/W319. ✓ Unit tests existed; gap closed this session: the literal acceptance "composite expands to list[Step] in a golden test" — added 09-composite-action.yml + .expanded.json and the test in test_actions.py.
A18 — templates/ + cmd_init.py: Jinja2 per-ecosystem templates, init --auto from the fingerprint, writes .gitignore for .yeet/tmp|runs|.secrets. ✓ test_templates.py covers auto-init/fingerprint (passed). Caveat: "yeet check on the result is clean" is still blocked by Dev D's pipeline stub — I verified layers 1–3 directly instead.
A19 — demo ./.yeet/actions/checkout/: Ship your own composite so the demo has zero external deps. ✓ Present at .yeet/actions/checkout/action.yml; also reused as the A17 golden fixture. Offline run still needs Dev C's executor wiring.
A20 — actions/resolver.py remote (stretch): owner/repo@ref → shallow git clone --depth 1 into ~/.yeet/actions/, cached by ref, failed clone = E313. ✓ Implemented with a test double for git_clone; unit-tested (resolve, cache hit skips clone, refs distinct, E313).
Blockers (external, not Dev A's code): yeet check/per-flow validity/offline run depend on Dev D's pipeline.validate_file and Dev C's executor, both still stubs. Net: 224 passed, 37 skipped.