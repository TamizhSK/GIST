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
| 9 | The installer's toolchain, parallel log attribution, W317 | uv can provision a Python; per-job log gutter |
| 10 | The runtime and the installer, found by running yeet on its own CI | `runs-on: ${{ matrix.os }}` was never interpolated |
| 11 | What `uses:` actually does — `--clean`, checkout, remote actions | four things green here and red on GitHub |
| 12 | Launch readiness audit — the full checklist, run rather than read | two false greens and a broken wheel, all fixed |

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

---

## Session 9 — the installer's toolchain, parallel logs, W317

### The installer could not do the one thing it most needed to

It required a suitable Python and could only print instructions when there
wasn't one — on a stock macOS box (system Python is 3.9) or a slim container,
that is where it stopped. `uv` is now preferred when present, and the reason is
not its speed: **it can provision a Python.** Verified with no suitable
interpreter on PATH at all — uv fetched 3.14.7 and the whole install took nine
seconds, after which a two-leg matrix with secrets and masking ran green on it.

uv builds OUR virtualenv rather than doing `uv tool install`, so the layout,
the shim and `yeet-uninstall` are identical whichever backend ran. One thing to
remove, in one place, however it got there. Falls back to `python -m venv`
(`YEET_NO_UV=1` forces it), and when neither is possible it now names both
fixes — the apt/brew line and uv, since uv is the shorter path. All three
branches tested.

### Parallel logs were true line by line and useless as a whole

A three-leg matrix printed three identical `+-- setup` headers and then
`using node 16`, `using node 18`, `using node 20` in whatever order the threads
reached the sink. Nothing said which leg any line came from.

Lines now carry a `job │ ` gutter once a run has more than one job, and nothing
before that — a single-job run is exactly as clean as it was, and that is safe
because a line emitted before a second job appeared could only have come from
the first. `grep 'node 18'` is now a complete log for that leg.

Found while fixing it: `_group_depth` was ONE shared counter while jobs emit
from parallel threads, so one job's `::group::` silently indented another
job's output, and either job's `::endgroup::` closed it.

### W317 — every registered code now has an implementation

`::set-output::`, `::save-state::`, `::set-env::`, `::add-path::`. A warning,
not an error, and that is the whole point: these still PARSE and now do
nothing, so a step ending `echo "::set-output name=sha::$(git rev-parse HEAD)"`
runs green on GitHub and produces no value — the job reading
`steps.x.outputs.sha` gets an empty string and fails somewhere else entirely.

The `::` sigil is required so prose about the migration is not flagged, and
current commands (`::group::`, `::add-mask::`, `::error::`) are untouched.
Zero hits across all nine real workflows in `tests/corpus/`.

### The panel had to fit the terminal

A fixed 72-column frame wraps on an 80-column window with anything in the
gutter. A wrapped box does not read as a narrow box, it reads as corruption.
Width now comes from `tput cols`, descriptions truncate to the derived column,
and below ~35 columns the box is dropped for a plain list. Checked at 100, 72,
60 and 40 columns and in the ASCII fallback.

### Still open

- **C15/C16** — docker and node actions are still skipped with a reason.
  `actions/checkout@v4` being a no-op is the user-visible consequence.
- **Built-ins run on the host**, not in the job's container (deliberate; the
  workspace is a bind mount).
- **A git-less install path.** The installer still needs git, because it
  installs from a git URL. A tagged release with a wheel would remove that and
  make "download a file" a real second option.
- **uv picks the newest satisfying Python** — 3.14 on this machine, which is
  ahead of the 3.10–3.13 CI matrix. It worked, but the first interpreter with
  no wheels for a C-extension dependency will find this out the hard way.
  Pinning the request to a tested range is the safer call if that happens.
- **`docs/` overlap** between handbook / understanding-yeet / getting-started.
- **Windows** verified by CI only; the 3.10 leg is new there.

### Verification

    make check        805 passed, six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py (56 rules)

Installer exercised in three environments: uv with no system Python, venv
fallback with uv declined, and neither available (the guidance path).


## Session 10 — the runtime, the installer, and what running it found

Four agents were dispatched over disjoint file sets; all four were killed
mid-edit by an account spend limit. Their surviving work was finished by hand
and is recorded here with what they left half-done, because the half-done parts
are the ones that bite.

### The bug that mattered: `runs-on: ${{ matrix.os }}` was never interpolated

Found by running yeet on its OWN CI workflow — a thing that had never been
done, and which took ten seconds to do. The image resolver read `job.runs_on`
RAW, so the literal string reached the runner-label table, matched nothing, and
every leg of a cross-platform matrix died with E315 "not a known runner label
or image". The leg knew its own value the whole time; nothing asked it.

Every cross-platform workflow in existence is written that way, so this was a
hard stop on most real files, and no unit test could have caught it: the tests
build a `Job` with a literal `runs_on`, which is the one case that works.

Expanded per leg on a COPY — the IR is shared across the plan and legs run in
parallel threads, so writing the value back would race and each leg would read
whichever landed last.

A second bug fell out of the first: a `local` leg inside a Docker run tried to
pull an image called "local". `runs-on: ${{ matrix.os }}` over
`[ubuntu-latest, local]` is ONE workflow with both kinds in it, and the backend
is chosen once for the whole run. Host legs now delegate to `LocalBackend`.

### The TUI, from a real screenshot

* **A built-in step never said it had finished.** `_run_builtin` emitted the
  step's output but not its lifecycle, and the live tree resolves a node on
  STEP_END. So `checkout` sat under a spinner for the rest of the run while its
  own result scrolled past above it. Only `run:` steps had ever sent those.
* **The summary panel was 111 columns** of mostly-empty box around two short
  rows, in ASCII `+---+` on a UTF-8 terminal. Capped at 70 — a caller passing
  the console width means "this is the room you have", not "fill it" — with
  box characters chosen by what the STREAM can encode, not by `LANG`, because
  a UTF-8 locale piped into a cp1252 file still raises.
* **The palette reached only the summary.** Job/step lines were still the basic
  sixteen while the summary was truecolour, so the closing line looked like it
  belonged to another program. Every line now goes through `paint()`.

### Docker failures that named the problem

`DockerFailure` and `daemon_is_gone` had been written and never raised — the
ninth instance of the unreachable-module pattern in this repo. Now the path for
every pull, build and create failure, with tables keyed on what the daemon
actually says: unreachable registry, no such image, auth, rate limit, no arm64
build, disk full, socket permissions, Docker Desktop file sharing, a name held
by an interrupted run.

`DockerUnavailable` was being caught per job, so a fourteen-job workflow
printed "cannot reach the daemon" fourteen times and exited 1 — "your workflow
failed". It is not the workflow. It propagates now and exits **3**, and the
message is words rather than docker-py's `('Connection aborted.',
FileNotFoundError(2, ...))`.

### Still open

- **Remote composite actions.** `owner/repo@ref` reports as unresolvable even
  though `resolve_remote` (A20) could fetch it. Deliberate: cloning from a
  `uses:` line reaches the network mid-run and needs its own decision about
  caching and offline behaviour. *(Done in session 11.)*
- **Windows** is verified by CI only. The 3.10 leg is new there, and the
  encoding-gated panel glyphs have never run on a cp1252 console. *(Session 11
  added the streams and the `windows-console` job — and found that the glyphs
  were gated on the wrong stream.)*
- **A git-less install** works via the GitHub tarball, but only for a GitHub
  URL. A tagged release with a wheel would make "download a file" a first-class
  path rather than a fallback.
- **`docs/` overlap** between handbook / understanding-yeet / getting-started.
- **The daemon dying MID-RUN** is translated but not reproduced end to end;
  `docker kill` of a live container during a step is untested.

### Verification

    make check        808 passed, six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py

Exercised by hand: a mixed `[ubuntu-latest, local]` matrix (both legs green),
checkout of a tag into `path:` via host git AND via a git container with git
removed from PATH, a toolchain mismatch failing loudly, DOCKER_HOST pointed at
a dead socket (exit 3, two lines, no traceback), and a full install from an
empty `$HOME` on a real pty.


## Session 11 — what `uses:` actually does

The goal this session was fidelity, stated plainly: a `uses:` line should do
locally what it does on GitHub. It did not, in four ways, and every one of them
was GREEN here and RED there — the direction a local runner must never get
wrong, because a false green ships.

### `--clean` was inert

`runner.py` built the isolated per-job workspace, handed it to
`JobContext.workspace`, and **neither backend ever read the field**. Both used
their own `self.root` for the bind mount, for `GITHUB_WORKSPACE` and for the
step loop. So `yeet run --clean` created an empty directory, ignored it, and
ran against the working tree exactly as before. The eleventh instance in this
repo of a finished thing with no call site, and the one that mattered most,
because fidelity is the flag's only purpose.

Reading it took a second mount. The step scripts and the five state files live
in `.yeet/tmp/<run>/<job>/`, which is outside an isolated workspace, so the job
scratch directory is now bound at `/yeet-run` and `to_step_path` points into
it. `storage/builtin.py` gets the real workspace too — otherwise
`upload-artifact` under `--clean` collects from the working tree rather than
from what the job just built.

Two more disagreements fell out of it. `${{ github.workspace }}` answered with
a HOST path inside a container while `$GITHUB_WORKSPACE` said `/workspace`;
they are interchangeable on GitHub and are now interchangeable here. And the
per-job workspace had to be written into a COPY of the github context —
`for_instance` uses `dataclasses.replace`, which copies shallowly, so the dict
is shared with every leg in the pool.

Verified by hand: a repo with one committed file and one uncommitted file. A
normal run sees both. `--clean` sees only the committed one, which is exactly
what GitHub would do.

### `actions/checkout` announced the opposite of what it did

Its default path printed "the workspace is already this repository" — true
under the bind mount, and a flat lie over an empty `--clean` workspace, after
which every step ran against nothing. It now fills the workspace from the
project root, which already has the objects, so the common case costs no
network. `fetch-depth: 0` is honoured (a shallow tree breaks `git describe
--tags` with an error that never mentions the checkout), and `outputs.commit`
carries the SHA instead of dropping it.

### The other three built-ins ignored the inputs that decide pass/fail

`if-no-files-found: error`, `fail-on-cache-miss`, `lookup-only`, v4's
`overwrite`, and `download-artifact` with no `name:` — which on v4 means EVERY
artifact and here meant one called `"artifact"` that usually did not exist, so
the step went green and the job failed later for an unrelated-looking reason.
All read now, with `cache-primary-key` / `cache-matched-key` / `download-path`
alongside.

### `owner/repo@ref` never resolved

`resolve_remote` had been written, tested, and never called. Wiring it needed
two things first.

It could not fetch the ref W402 tells you to use: `git clone --depth 1 --branch
<ref>` cannot check out a commit SHA, so the PINNED spelling failed 100% of the
time. It goes through `actions/fetch.py` now — init + fetch + checkout, the one
sequence that treats a branch, a tag and a SHA identically.

And a `uses:` line reaching the network mid-run needed a stated policy rather
than a default nobody chose. Fetch on a cache miss, announced on the step's own
line; cache under `cache_dir()/actions/<owner>/<repo>/<ref-slug>`, forever for
a SHA or an exact tag and for 24h for a moving `@v4`; `--offline` (or
`YEET_OFFLINE=1`) to refuse the network and report the miss against the
workflow line that caused it; `yeet prune --actions` to empty it. Which refs
move now lives in `core/refs.py` so the lint and the cache cannot drift apart —
they are at different tiers and a copied list could not have been kept honest.

Running a real one found three more things, all of which are why this is worth
doing against real actions rather than fixtures:

* **`${{ inputs.x }}` inside a composite resolved to `""`.** `$INPUT_X` in the
  env always worked, so the shell form was fine and the expression form was a
  silent empty string — two spellings of one value, one of them a lie.
* **`uses: ./x` inside a composite** resolved against the workspace. For a
  cached action that is a different repository entirely.
* **A built-in got CONTAINER paths.** A real action computes from
  `${{ runner.temp }}`, hands `/workspace/...` to `upload-artifact`, and the
  built-in runs on the host — so it reported "no files matched" for a file that
  had just been written.

`actions/upload-pages-artifact` pinned to a 40-hex SHA now runs end to end:
fetched, inlined, its per-OS `if:` conditions evaluated, its tar written, and
its own nested `uses: actions/upload-artifact@v4` served by our built-in.

### cp1252, and a bug that was hiding behind the note

`undone.md` said Windows was "verified by CI only" and that the panel glyphs
had never run on a cp1252 console. Writing the test that says so found the bug:
`format_summary` chose its box characters by asking **`sys.stdout`** while both
renderers write to **`self.out`**. On a UTF-8 console piped into a cp1252 file
it asked the console, got the box, and raised writing it to the file. The
encoding gate was real and pointed at the wrong stream.

`tests/unit/test_console_encoding.py` writes to real cp1252 and cp437 streams
with `errors="strict"`, and drives the CLI through subprocesses with
`PYTHONIOENCODING=cp1252:strict`. That is not a simulation: it is the same
`TextIOWrapper` encoder Windows uses, so it is evidence anywhere it runs.

### Still open

- **Docker and node actions (C15/C16).** Now fetched and READ, so the skip
  names which kind it is instead of claiming the action could not be resolved.
  Running them is the next real step, and `runs.using: docker` is the closer of
  the two — the Docker plumbing is all here.
- **`artifact-url` is not emitted** by `upload-artifact`. There is no service
  and no URL that would resolve, and a plausible-looking dead link is worse
  than a missing field.
- **The Windows CONSOLE** is now exercised by the `windows-console` CI job
  (redirected output under `chcp 1252`, plus `PYTHONLEGACYWINDOWSSTDIO`), which
  is the part no Mac can reach. What nothing automated answers is whether a
  given console FONT has a glyph for a character it can encode.
- **A git-less install**, **`docs/` overlap**, and **the daemon dying mid-run**
  are unchanged from session 10.

### Verification

    make check        920 passed, six gates green
    pytest -m docker  18 passed against a live daemon

By hand, against a real repository and a real marketplace action:

* `yeet run` — unchanged, which was the regression that mattered most.
* `yeet run --clean` — empty workspace, checkout fills it, uncommitted files
  correctly absent, both spellings of the workspace agreeing.
* `uses: actions/upload-pages-artifact@56afc609...` (a 40-hex SHA) — fetched,
  inlined, green. Re-run: cache hit, no network. `--offline` on a cold cache:
  one clear line naming the cache path.
* A composite calling `./nested`, and `${{ inputs.path }}` resolving.

---

## Session 12 — the launch readiness audit

Worked the checklist in [`docs/audit/prompt.md`](../audit/prompt.md) end to
end, running every proof command rather than reading for intent. The full
report with evidence is [`audit/report.md`](../audit/report.md); this is what
it cost and
what it found.

### Two false greens, which is the failure mode that matters

A local runner exists so the push is the second time you find out. Both of
these made it the first time again, and both passed every gate in the repo.

**The dialect rewrite was mistranslating canonical GitHub Actions files.**
`normalize()` walked the whole tree and rewrote any key it recognised, which is
correct wherever keys come from the schema and wrong wherever they are the
user's own words. So a real `.github/workflows` file containing
`with: {when: always}` reached the executor as `with: {on: always}` — a
different input to a marketplace action — and `env: {where: x}` became
`working-directory`. It also set `used_dialect=True`, so the file was told it
was written in a dialect it contained none of.

The audit predicted this one in its own text (§8.4) and it was there. The fix
is a scope table: the rewrite descends into `jobs`, a job, a step, `strategy`,
`container`, `services` and `defaults`, and into nothing else. `with:`,
`env:`, `matrix:`, `secrets:`, `outputs:` and the job IDs under `jobs:` are
reached through an `opaque` default, so a schema key nobody has listed yet is
left alone — the safe direction to be wrong in. `find_collisions` shares the
walk, because it had the same bug in the other direction: it reported
`with: {name: a, vibe: b}` as one key spelled two ways, and refused a valid
workflow.

**`yeet check` was validating files it had never opened.** It had its own
two-line discovery — `glob("*.yml")` in `.yeet/flows` and `.github/workflows` —
while `yeet scan` used `analyzer.discover`. On a project written with `.yaml`,
or with a bare `workflows/` at the root:

    $ yeet scan
    flows found: 2
    $ yeet check ; echo $?
    No workflow files found in .
    0

Exit 0 from the command people wire into a pre-push hook. It calls
`discover_flows` now, and a clean run prints a summary line instead of nothing
at all — printing nothing was indistinguishable from finding nothing, and those
had different meanings and the same exit code.

### The wheel did not contain what the wheel needed

Every CI job ran `pip install -e`, which is the one configuration no released
user is ever in. Under it, `Path(__file__).parents[3]` reaches the repo root
and every data file resolves. Installed, it reaches the directory beside
site-packages and none of them do.

So `Dockerfile.base` was unreachable and `yeet run` told installed users to run
`make image` in a project they had never cloned, and `docs/rules.md` was
unreachable and `yeet explain` printed a two-line stub pointing at `make
rules`. Both files are force-included into `yeet/_data/` now and read through
`importlib.resources`; there is still exactly one of each on disk, so `make
image` and an installed `yeet run` cannot build different images.

`twine check --strict` also failed outright — no `readme`, so the PyPI page
would have been blank, and no license, author, URLs or classifiers. The
`packaging` CI job is the part that stops this recurring: build the artifact,
assert the four data files are inside it, install it into a venv, `cd` to a
directory with no repo above it, and run the two commands that read them.

### CI was red on two platforms for reasons neither test was about

**macOS.** Seven tests failed because `_extract` refused to unpack a cache
tarball when `TarFile.extractall` had no `filter=`. The refusal was
deliberate — falling back silently is how a security fix becomes optional —
but the conclusion was wrong: `actions/setup-python` ships **3.10.11** as the
newest 3.10 for macOS, because python.org stopped building macOS installers
after it, and that is one patch below the backport. A supported platform, on a
supported interpreter, could not restore a cache. The `data` filter's rules are
applied by hand there now, every member validated before anything is written,
and four tests force that branch on an interpreter that does not need it.

**Windows.** `test_console_encoding.py` built its subprocess environment by
hand, so the child had no `SystemRoot` (the interpreter dies before `main()`,
unable to seed hash randomisation) and no `USERPROFILE`. The second one was a
real product bug wearing a test bug's clothes: `Path.home()` **raises** rather
than guessing, and both `analyzer/root.py` and `expressions/contexts.py` used
it as the stop condition for an upward walk. A git hook, cron and Task
Scheduler all run with a stripped environment, so `yeet scan` from a hook ended
in a traceback. `core.config.home_dir()` returns `None` now and the walk stops
at the filesystem root.

### Things that were finished and unreachable — the twelfth and thirteenth

`analyzer.discover` had every behaviour §7 asks for, and the command that most
needed it was not calling it. `DockerFailure`, `daemon_is_gone`, `--clean`,
`resolve_remote` — this is the same shape as sessions 10 and 11, and it is now
the most reliable predictor of a bug in this repo. The audit found two more by
asking "what calls this?" rather than "does this work?".

### What is new rather than fixed

`yeet doctor`, which the checklist calls the highest-value item in its section
and was right to: Python, PATH (including a *second* yeet shadowing this one),
Docker with a per-platform fix line, git, config and cache writability, and
WSL's `/mnt/c` slow path. Exit 1 if anything would stop a run. A test asserts
that every failing check carries a fix, because a failure with no next step is
the support ticket it exists to prevent.

`install.ps1`, so the Windows one-liner in the README points at something.
`release.yml`, so a `v*` tag builds, verifies the tag matches `__version__`,
installs the artifact in a clean venv, runs it, and attaches the wheel and
sdist to a draft release — which closes "a git-less install", open since
session 9. And `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md` and issue templates that ask for `yeet doctor` output.

### A guard that could not see what it was guarding

`test_ascii_output.py` greps source lines containing `typer.echo(`. `--help` is
built from the `help=` kwarg and from command **docstrings**, neither of which
it read, so an em dash sat in `yeet --help` and five subcommands with the file
green throughout. It asserts on *rendered* help for all twelve commands now.
Verified by reverting the string and watching it fail.

### Still open

- **Windows and WSL have never been touched by a human on this team.** CI
  parses `install.ps1`, lints it with PSScriptAnalyzer and runs it end to end
  under PowerShell 5.1, but a green runner is not a user's laptop. Three of the
  five platforms in the §11 matrix have no owner. This is the only thing left
  that blocks a tag, and it is scheduling rather than engineering.
- **No demo GIF.** §12.12 argues this determines whether anyone tries the tool
  and is probably right.
- **The `--tui` dashboard is the least-verified surface** — resize and renderer
  fuzzing are both untested. The audit recommends shipping it marked
  experimental rather than delaying for it.
- **The installer wordmark is hand-typed in both scripts** while
  `tools/gen_logo.py` is the single source for the SVG. Three copies now.
- **No TestPyPI dry run**, and the package is not on PyPI — both installers use
  a git URL.
- **The daemon dying mid-run** is translated but still not reproduced end to
  end. Unchanged since session 10.

### Verification

    make check        1010 passed, six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py
    python -m build   twine check --strict PASSED on wheel and sdist

By hand: the wheel and the sdist each installed into a clean venv and driven
from a directory with no repo above them; `yeet check` against a `.yaml`
project and a bare `workflows/` root; a canonical workflow with `when`,
`after` and `where` at every user-data position, asserted byte-for-byte
unchanged; `env -i PATH=... yeet --version`; and `yeet doctor` against a dead
`DOCKER_HOST`.
