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