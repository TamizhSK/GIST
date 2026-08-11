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