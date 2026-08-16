# YEET Launch Readiness Audit — 2026-08-16

Audited against [`prompt.md`](prompt.md). Everything
marked PASS was **run**, not read. Where
this machine (macOS 14, Apple Silicon, Docker 29.6.2, Python 3.12.0) could not
reach a configuration, the row says `UNVERIFIABLE HERE` and names the command a
human must run and what correct output looks like.

Findings that were fixed in this pass are marked **FIXED** with the commit that
did it. The rest are open and ranked.

## Verdict

**SHIP WITH CAVEATS.** The correctness core is now sound and it was not when
this audit started: the dialect rewrite was silently mistranslating *canonical*
GitHub Actions files, and `yeet check` was reporting exit 0 on projects whose
workflows it had never opened. Both were false greens, both are fixed, and both
now have tests that fail on the old behaviour. Packaging was equally broken —
the wheel shipped without `Dockerfile.base` or `rules.md`, so the two commands
that read them worked for the four people with a clone and for nobody else.
That is fixed and proven from a real installed wheel. What is left is not
correctness: it is that Windows and WSL have never been touched by a human on
this team, `install.ps1` was written this session and has run in CI only, and
there is no demo GIF. Tag `v0.1.0` and publish once one person has followed the
README on a real Windows box and one on WSL. Nothing else blocks.

---

## P0 — blocks launch

| # | Finding | Section | Evidence | Fix | Est |
|---|---|---|---|---|---|
| P0-1 | **Aliases were rewritten everywhere, including where keys are user data.** A canonical workflow with `with: {when: always}` parsed as `with: {on: always}`; `env: {where: x}` became `working-directory`; a matrix variable named `when` became `on`; a job ID could be renamed. The file also reported itself as dialect. | §8.4, §8.5 | Probe output in [below](#p0-1-detail); `tests/unit/test_alias_scope.py` (27 cases) fails on the old code | **FIXED** — `_SCOPES` in `parser/aliases.py`: the rewrite descends only into positions whose keys come from the schema. `find_collisions` shares the walk. | done |
| P0-2 | **`yeet check` found no workflows and exited 0** where `yeet scan` found two. Its own two-line discovery globbed `*.yml` in two hardcoded directories, so `.yaml`, a bare `workflows/`, and every nested layout returned "No workflow files found" — exit 0. A false green in the command wired into pre-push hooks. | §7.1, §7.3, §7.12 | Reproduction in [below](#p0-2-detail); `tests/unit/test_check_discovery.py` | **FIXED** — `cmd_check` now calls `analyzer.discover_flows`, the same walk `scan` uses. | done |
| P0-3 | **The wheel did not contain `Dockerfile.base` or `docs/rules.md`**, and both were located by `Path(__file__).parents[3]`, which is the repo root from a checkout and site-packages' parent from an install. `yeet run` told installed users to run `make image` in a project they had never cloned; `yeet explain` printed a two-line stub pointing at `make rules`. | §2.2, §2.4, §5.7 | `find_base_dockerfile()` returned `None` from a clean-venv wheel install | **FIXED** — `force-include` into `yeet/_data/`, read through `core/resources.py` (`importlib.resources`). Verified from a real wheel and a real sdist. | done |
| P0-4 | **`twine check --strict` failed**: no `readme`, so the PyPI page would have been blank. No license, author, URLs, keywords or classifiers either. | §2.5, §2.6, §12.1 | `twine check --strict dist/*` → `FAILED due to warnings` | **FIXED** — full `[project]` metadata, `LICENSE` (MIT), `[project.urls]`. `twine check --strict` now PASSED on both artifacts. | done |
| P0-5 | **No Windows installer existed.** §3's requirement is one line per OS; only `install.sh` was in the repo, and the README offered no Windows path at all. | §3, §12.14 | `ls install.*` → `install.sh` only | **FIXED** — `install.ps1`, plus an `installer-windows` CI job that parses it under both PowerShell editions, runs PSScriptAnalyzer, and installs twice to prove idempotence. **Never run by a human.** | done |
| P0-6 | **CI was red on macOS**: 7 tests failed because `_extract` refused to extract when `TarFile.extractall` had no `filter=`. `actions/setup-python` ships **3.10.11** as the newest 3.10 for macOS — python.org stopped building macOS installers after it — which is one patch below the backport. | §1.10, §2.11 | The pasted macOS CI log | **FIXED** — `_extract_checked` applies the `data` filter's rules by hand, validating every member before writing any. Four new tests force that branch on this interpreter. | done |
| P0-7 | **CI was red on Windows**: the console-encoding tests built a hand-made POSIX env, so the child had no `SystemRoot` (`Fatal Python error: _Py_HashRandomization_Init`) and no `USERPROFILE` (`RuntimeError: Could not determine home directory`). | §1.9, §6.7 | The pasted Windows CI logs | **FIXED** — the test inherits and overrides. The *product* half is P1-1. | done |

<a name="p0-1-detail"></a>

### P0-1, before and after

Input is 100% canonical GitHub Actions — no dialect anywhere:

```yaml
jobs:
  build:
    env: {where: /opt/app}
    steps:
      - uses: some/action@v1
        with: {when: always, after: build, where: ./src}
    strategy:
      matrix: {when: [a, b]}
```

Before (`normalize()` output, `used_dialect=True`):

```yaml
    env: {working-directory: /opt/app}
        with: {on: always, needs: build, working-directory: ./src}
      matrix: {on: [a, b]}
```

After: byte-for-byte unchanged, `used_dialect=False`.

<a name="p0-2-detail"></a>

### P0-2, the reproduction

```console
$ ls workflows/ .github/workflows/
workflows/w.yaml   .github/workflows/g.yaml

$ yeet scan
flows found: 2

$ yeet check ; echo "exit=$?"
No workflow files found in .
exit=0
```

Now: `[OK] 2 flows checked: 0 error(s), 2 warning(s)`, exit 0, with both files
actually validated.

---

## P1 — fix this week

| # | Finding | Section | Evidence | Fix | Est |
|---|---|---|---|---|---|
| P1-1 | **`Path.home()` crashed the CLI in a stripped environment.** `analyzer/root.py` and `expressions/contexts.py` both used it as the stop condition for an upward walk. A git hook, cron, or Task Scheduler on Windows has no `USERPROFILE`, and `Path.home()` raises rather than guessing — so `yeet scan` from a hook ended in a traceback. | §6.7, §6.8 | The Windows CI traceback; `tests/unit/test_stripped_env.py` | **FIXED** — `core.config.home_dir()` returns `None` instead, and the walk stops at the filesystem root. | done |
| P1-2 | **`python -m yeet`'s module body ran the whole CLI on import.** Any package walk — `pkgutil`, import-linter, a docs builder — executed `main()`. Visible in `lint-imports` output, which printed the banner and the help before its own report. | §1.2, §1.3 | `python -c "…walk_packages…"` printed the help | **FIXED** — `if __name__ == "__main__":`. | done |
| P1-3 | **A stale duplicate tree was tracked at the repo root.** `yeet/` held an older `layer3_semantic.py`, an older `test_layer3.py`, and a 46 KB internal `session-context.md`. A merge artifact, and it would have shipped in the sdist and been the first thing a reader browsing the repo saw. | §12.3 | `git ls-files yeet/` | **FIXED** — deleted. | done |
| P1-4 | **`--help` was not ASCII**, and the guard that was supposed to catch that could not see it. `test_ascii_output.py` greps source lines containing `typer.echo(`; `--help` is built from the `help=` kwarg and from command **docstrings**, which it never read. An em dash reached `yeet --help` and five subcommands. | §4.6 | `yeet --help` contained `—`; the new test fails on the old string (verified by reverting it) | **FIXED** — strings corrected, and the guard now asserts on *rendered* help for all 12 commands, excluding the box characters rich picks by encoding. | done |
| P1-5 | **`--version` printed one line.** §5.8 wants version + Python + OS + Docker, and those were the three follow-up questions on every report. | §5.8 | `yeet --version` → `yeet 0.1.0` | **FIXED** — four lines. `install.sh` takes `head -1`. | done |
| P1-6 | **No `yeet doctor`** — "the highest-value item in this section". | §5.9 | not in `yeet --help` | **FIXED** — `cmd_doctor.py`: Python, PATH (including a *second* yeet shadowing this one), Docker with a per-platform fix, git, config/cache writability, and the WSL `/mnt/c` slow-path warning. Exit 1 if anything would stop a run. Every failing check is asserted to carry a fix. | done |
| P1-7 | **`--format json` printed nothing on a clean run**, so a consumer parsing the output failed on the common case. | §8.13 | `yeet check --format json` → empty | **FIXED** — always valid JSON; canonical keys confirmed (`"severity": "warning"`, never `flopped`). | done |
| P1-8 | **Version was declared twice** — `pyproject.toml` and `src/yeet/__init__.py`. One release from a wheel whose filename and `--version` disagree. | §2.8 | `grep -rn "0\.1\.0"` → 2 hits | **FIXED** — `[tool.hatch.version]` reads `__init__.py`. The release workflow also fails if the tag disagrees with the built version. | done |
| P1-9 | **No `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, or issue templates.** | §12.1, §12.7–12.11 | `ls` | **FIXED** — all added. The bug template asks for `yeet doctor` output as its first, required field. | done |
| P1-10 | **`install.sh` had no `--version` pin and no `--local`.** Both were env-var-only (`YEET_REF`), which the README did not mention and `sh -s --` cannot reach. | §3.10, §3.12 | no arg parsing in the script | **FIXED** — `--version <ref>`, `--local`, `--help`. `--local` refuses with a clear message under `curl \| sh`, where `$0` is `sh`. | done |
| P1-11 | **No release automation, and no tagged artifact.** `undone.md` has had "a git-less install" open since session 9; the missing half was a release with a wheel attached. | §12.13 | no `release.yml` | **FIXED** — `.github/workflows/release.yml` on `v*`: build, `twine check --strict`, assert tag == `__version__`, install the artifact in a clean venv and run it, then a **draft** release with the wheel and sdist attached. | done |
| P1-12 | **Nothing tested the built artifact.** Every CI job ran against `pip install -e`, the one configuration no released user is ever in. That is what hid P0-3. | §2.2, §2.3 | CI had no packaging job | **FIXED** — a `packaging` job on all three OSes: build, `twine check --strict`, assert the four data files are in the wheel, install into a venv, `cd` somewhere with no repo above it, and run `yeet explain` and the Dockerfile lookup. | done |
| P1-13 | **`install.ps1` has never run on a real Windows machine.** It is new this session. CI parses it, lints it with PSScriptAnalyzer, and runs it end to end under Windows PowerShell 5.1 — but a green runner is not a user's laptop, and the runner's PATH, proxy and Docker Desktop state are all unlike theirs. | §3, §11 | `UNVERIFIABLE HERE` — no Windows and no `pwsh` on this machine | **OPEN.** One teammate runs the README's `irm … \| iex` on a real Windows 11 box and pastes the terminal output into the tracking issue. | 1h |
| P1-14 | **WSL is entirely unverified.** The `/mnt/c` warning, the Docker Desktop integration message, and git hooks under Git for Windows are all written and none has been run. | §11 | `UNVERIFIABLE HERE` | **OPEN.** `yeet doctor` under WSL with a repo on `/mnt/c` and again under `~/`; toggle Docker Desktop's WSL integration off and confirm the message names the checkbox. | 1h |

---

## P2 — post-launch

| # | Finding | Section | Evidence | Fix | Est |
|---|---|---|---|---|---|
| P2-1 | Three `__file__` lookups remain, all resolving *inside* the package: `aliases.yml`, the j2 template dir, `workflow.schema.json`. Correct for a normal install and broken in a zipapp. jinja2's `FileSystemLoader` has the same constraint. | §2.4 | `grep -rn "__file__" src/` | Move to `importlib.resources` if a zipapp is ever a target. It is not one today, and saying so is the justification §2.4 asks for. | 1h |
| P2-2 | The installer's closing panel lists four commands; §5.1 asks for **one** copy-pasteable next command. `install.ps1` lists five, including `yeet doctor`. | §5.1 | the tail of both installers | Pick one. `yeet doctor` is the right one — it is the only one that works before the user has a project. | 20m |
| P2-3 | No shell completion for bash/zsh/fish/PowerShell. `add_completion=False` is set explicitly on the Typer app. | §5.10 | `src/yeet/cli/app.py:36` | Typer gives this for free; the flag was turned off deliberately and never revisited. | 30m |
| P2-4 | No `yeet help` command. `yeet`, `yeet --help` and `yeet -h` are consistent and useful; `yeet help` is not a command. | §5.4 | `yeet help` → "No such command" | One alias, or drop the requirement — the three that exist already agree. | 15m |
| P2-5 | The installer wordmark is hand-typed in `install.sh` **and** in `install.ps1`, while `tools/gen_logo.py` is the single source for `assets/yeet.svg` and `assets/yeet.txt`. Three copies now, up from two. | §4.10 | `banner()` in both scripts | Generate both installers' banner rows from `assets/yeet.txt`, or accept the drift and add a test comparing them. | 1h |
| P2-6 | No 30-second GIF or asciinema in the README. §12.12 calls this the thing that determines whether anyone tries it, and it is the largest single gap left. | §12.12 | the README | Record `scan → check → run` on a green run. | 1h |
| P2-7 | Contributor emails in git history include an institutional student address. Normal for a public repo, but it is a real identifier and worth a deliberate decision rather than a default. | §12.3 | `git log --format='%ae' \| sort -u` | Team decides. Rewriting history for this is almost certainly not worth it. | 10m |
| P2-8 | The 3.10 floor is real but under-tested at the patch level. macOS CI gets 3.10.11; Ubuntu 22.04 originally shipped 3.10.6. P0-6's fallback is exactly the kind of thing that will be needed again. | §2.11 | the macOS CI log | Keep the habit: when a stdlib feature is version-gated, implement the fallback rather than refusing. | — |
| P2-9 | No TestPyPI dry run, and the package is not on PyPI. Both installers use a git URL. | §2.12 | — | Do it before the first `pip install yeet` appears in any documentation. | 30m |

---

## Section results

```
§1  base level          PASS 10/10 · FAIL 0 · UNVERIFIABLE 0      (2 found, both fixed)
§2  packaging           PASS 10/12 · FAIL 0 · UNVERIFIABLE 2      (4 found, all fixed)
§3  one-line install    PASS 11/15 · FAIL 0 · UNVERIFIABLE 4
§4  install TUI         PASS  7/11 · FAIL 1 · UNVERIFIABLE 3
§5  discoverability     PASS  8/10 · FAIL 2
§6  isolation           PASS  8/9  · FAIL 0 · UNVERIFIABLE 1      (1 found, fixed)
§7  discovery           PASS 13/14 · FAIL 0 · UNVERIFIABLE 1      (1 found, fixed)
§8  dialect             PASS 14/14 · FAIL 0                       (2 found, both fixed)
§9  real-world Docker   PASS 12/17 · FAIL 0 · UNVERIFIABLE 5
§10 run TUI / logging   PASS 13/15 · FAIL 0 · UNVERIFIABLE 2
§11 cross-platform      1 of 5 platforms verified
§12 launch gate         PASS 12/15 · FAIL 1 · UNVERIFIABLE 2      (5 found, all fixed)
```

### §1 — base level

All ten pass now. Two did not:

- **1.2/1.3 FAIL → FIXED.** `src/yeet/__main__.py` called `main()` at module
  level. `python -c "…walk_packages…"` printed the full CLI help; `lint-imports`
  printed the banner before its own report. Import time for `yeet.cli.app` is
  137 ms, under the 200 ms bar — `typer` is 37 ms of it and unavoidable.
- **1.6 PASS.** Three grep hits, all false positives: the word `print()` in a
  docstring, and `fingerprint(` twice.
- **1.4/1.5 PASS.** 2 contracts kept, 0 broken, 107 files, 258 dependencies.
- **1.9/1.10 PASS.** `1010 passed, 18 deselected` and `18 passed` against a live
  daemon.

### §2 — packaging

Four failures, all fixed; the two remaining are unverifiable here.

- **2.2/2.4 FAIL → FIXED.** See P0-3.
- **2.5/2.6 FAIL → FIXED.** See P0-4. `METADATA` went from 973 bytes to 15 KB.
- **2.8 FAIL → FIXED.** See P1-8.
- **2.3 PASS.** sdist installs in a clean venv and `yeet explain YEET-E301`
  prints the real section from the packaged `rules.md`.
- **2.9 PASS.** Lower bounds everywhere, no upper caps. `tomli` is correctly
  conditional on `python_version < "3.11"`.
- **2.10 PASS.** 258 KB wheel, 448 KB sdist, both well under 5 MB.
- **2.11 UNVERIFIABLE HERE.** The CI matrix covers 3.10–3.13 × 3 OSes. Run:
  `gh run list --workflow=CI` after pushing; all twelve legs must be green.
- **2.12 UNVERIFIABLE HERE.** `twine upload -r testpypi dist/*`, then
  `pip install -i https://test.pypi.org/simple/ yeet` in a clean container.
  Correct output: `yeet --version` prints four lines and `yeet doctor` runs.

### §3 — one-line install

`install.sh` is genuinely good: `set -eu`, POSIX `sh` rather than bash, no
`sudo`, a uv fast path that can *provision* a Python, a git-less tarball
fallback, a per-shell PATH line, and a `yeet-uninstall` that exists.

- **3.1–3.7, 3.11 PASS** by reading and by running `--help`/`--local` locally.
  3.2 is idempotent by construction: the profile is grepped for `$BIN_DIR`
  before appending.
- **3.10, 3.12 FAIL → FIXED.** See P1-10.
- **3.13, 3.14 FIXED** (`install.ps1` + the README's `-ExecutionPolicy Bypass`
  line), **but see P1-13** — CI-only.
- **3.3, 3.9 UNVERIFIABLE HERE.** musl/Alpine and arm64 are now in the
  `installer-posix` CI matrix; a corporate proxy is not. Run:
  `HTTPS_PROXY=http://proxy:8080 sh install.sh` on the work laptop.
- **3.15 PARTIAL.** The README shows how to download and read the script before
  running it, which is the minimum the check allows. No checksum, no signature.

### §4 — install TUI

- **4.2 PASS, and the design is right.** The script asks two *separate*
  questions — "may I use colour" (`[ -t 1 ]` and `NO_COLOR` and `TERM`) and
  "may I use box-drawing characters" (the locale). Conflating those is the
  usual bug and this code has a comment explaining why it does not.
- **4.3, 4.4 PASS.** `NO_COLOR=1`, `TERM=dumb` and a pipe all produce zero
  escape sequences from the CLI.
- **4.5 PASS.** `COLUMNS=60 yeet --help` → 0 lines over 60 characters.
- **4.6 FAIL → FIXED.** See P1-4.
- **4.8 PASS.** A real `[n/4]` step counter, not a fake progress bar.
- **4.1, 4.7 UNVERIFIABLE HERE.** No Windows Terminal, `cmd.exe`, PowerShell
  ISE, or GNOME Terminal on this machine. Run each installer in each and
  photograph the banner.
- **4.10 FAIL, accepted as P2-5.**

**Cool Developer note.** The wordmark is genuinely good and it is the best
thing in the repo's presentation. Six rows of `█`, one colour per row, indigo
at the cap-height down to a low-sun amber at the baseline — it reads as one
object rather than as coloured text, the counters in the E's are open enough to
survive at small line-heights, and the letterforms are wide enough that the
gradient has room to do something. It is legible at a glance, which is the only
test that matters at 2 a.m.

Two honest criticisms. First, the tracking is loose: `Y E E T` at four
characters of gap in the ASCII fallback reads as four letters rather than a
word, and the fallback deserves the same care the block version got. Second,
the panel at the end is doing more work than the moment needs — after four
steps of output, a box with four rows in it is a fifth thing to read when the
user already knows it worked. §5.1 is right that it should be one line. Cut
the box, keep the wordmark.

### §5 — discoverability

- **5.5 PASS.** `yeet chekc` → "Did you mean 'check'?", from typer.
- **5.7 PASS** (after P0-3 — it printed a stub from a wheel before).
- **5.8 FAIL → FIXED**, **5.9 FAIL → FIXED**. See P1-5, P1-6.
- **5.1 FAIL, accepted as P2-2. 5.10 FAIL, accepted as P2-3. 5.4 partial,
  P2-4.**
- **5.2, 5.3 PASS.** Commands are listed with one-line descriptions, and the
  order is task order rather than alphabetical: scan → check → explain → init →
  run → graph → logs → watch → prune → hooks → secrets → doctor.
- **5.6 PARTIAL.** Every subcommand has `--help`; not all carry a worked
  example. `doctor` does.

### §6 — isolation

**The spec's premise is wrong and the repo already knows it.** §6 asks yeet to
"automatically apply its venv" in the user's project. That would shadow the
project's interpreter and turn a workflow's `pip install` into a mutation of
yeet's own environment. The right model is an isolated application with one
shim on PATH, and that is exactly what `install.sh` builds — a private venv
under `~/.local/share/yeet` and an `exec` shim in `~/.local/bin`. No pushback
needed; it was designed correctly. §6's own table tests the right thing.

Proofs run:

```console
$ cd /tmp && yeet --version                     # 6.1
yeet 0.1.0
$ . /tmp/othervenv/bin/activate                 # 6.2, with a conflicting ruamel.yaml
$ yeet check .../sample_project ; echo $?
0
$ env -i PATH=/usr/bin:/bin $(command -v yeet) --version   # 6.7
yeet 0.1.0
```

- **6.7/6.8 FAIL → FIXED.** See P1-1. This is the one §6 item that was actually
  broken, and Windows CI found it by accident.
- **6.4 PASS.** All four paths are gitignored and `yeet init` writes the block.
- **6.5 PASS.** `platformdirs` throughout; the `Path.home()` fallbacks are only
  reached if it is missing, and they no longer raise.
- **6.9 UNVERIFIABLE HERE** on Windows; the hook shim resolves an absolute path
  on POSIX.

### §7 — discovery

`analyzer/discover.py` is the strongest module in the repo for this section:
depth cap with a documented exemption once inside a flow directory, a file cap,
an inode set for symlink loops, `PermissionError` tolerance, an exclude list, a
`.gitignore` spec, and foreign-CI detection. Every one of 7.7–7.13 is covered
by it and by `tests/unit/test_discovery_layouts.py`.

- **7.1/7.3/7.12 FAIL → FIXED** — but only for `yeet check`, which was not
  using this module at all. See P0-2. `scan` was always correct.
- **7.14 PASS.** Zero flows prints the fingerprint and suggests
  `yeet init --auto`, exit 0.
- **7.4 PASS but under-documented.** Nested `workflows/` in a monorepo *are* in
  scope (MAX_DEPTH 6, chosen for `apps/<svc>/<pkg>/.github/workflows/`). The
  audit is right that this needs saying out loud in the README; it currently
  only exists as a comment in the module.
- **7.6 UNVERIFIABLE HERE.** Case-insensitive matching cannot be distinguished
  from a case-insensitive filesystem on macOS. Run the layout tests on Linux.

### §8 — dialect

Now the best-tested section, which is the right outcome for the highest-risk
area.

- **8.4, 8.5 FAIL → FIXED.** See P0-1. This is the finding the audit predicted
  in its own text, and it was real.
- **8.3 PASS, now enforced.** No alias shadows a real Actions key — asserted
  against `workflow.schema.json` rather than against anyone's memory, so a new
  alias that collides is a red build.
- **8.2 PASS.** The table is deliberately *not* injective (`bet`/`cook` both
  mean `run`) and `find_collisions` catches two spellings in one mapping. Now
  tested by generating a colliding file for every such pair in `aliases.yml`.
- **8.7 PASS.** `test_dialect_parity.py` round-trips through the real
  `validate_file` entry point, not through hand-composed stages — which is the
  detail that matters, since the historical bug was a missing call site.
- **8.11 PASS.** Nothing inside `${{ }}` is a key, so the rewrite cannot reach
  it; now structurally true rather than incidentally true.
- **8.12/8.13 PASS.** `--format json` emits `"severity": "warning"`, never
  `flopped`. 8.13's empty-output bug is P1-7.
- **8.1 PASS.** Nine real OSS workflows in `tests/corpus/` parse clean. The
  audit asks for ten; adding one is trivial and worth doing.
- **8.14 PARTIAL.** The dialect table is in the README but hand-written, so it
  can drift from `aliases.yml`. Same class of problem as P2-5.

### §9 — real-world Docker

18 Docker-marked tests pass against a live daemon (96 s). What could not be
reached from this machine:

- **9.3 UNVERIFIABLE HERE.** GitHub's unauthenticated rate limit. Run:
  `for i in $(seq 61); do …` or wait one out, and confirm the message names
  `GITHUB_TOKEN` rather than printing a 403.
- **9.4/9.5 UNVERIFIABLE HERE.** Docker Hub anonymous rate limiting and a
  private GHCR image. Both message paths exist in `backend.py`'s table.
- **9.11 UNVERIFIABLE HERE.** File ownership after a run is a Linux/WSL
  question; `docker_user()` returns `None` on macOS by design. Run on Linux:
  `yeet run && git status` — must be clean.
- **9.17 PASS.** `services:`, `container:` and `concurrency:` produce
  diagnostics rather than being ignored, which the audit correctly calls a
  correctness issue.
- **The daemon dying mid-run** is translated but still not reproduced end to
  end — carried over from `undone.md` session 10 and still open.

### §10 — run TUI and logging

The code-frame renderer is better than it needed to be — see below. Not
reachable here:

- **10.5 UNVERIFIABLE HERE.** Terminal resize mid-run needs a human at a
  terminal. Run: start a long `yeet run --tui`, drag the window narrower.
- **10.12 PARTIAL.** The renderer clamps bad positions and there are tests for
  it, but nobody has fuzzed it. Worth an hour with `hypothesis` on random
  line/col against empty files and 10k-character lines.
- **10.14 PASS.** `yeet check > out.txt 2>&1` → `ASCII text`, zero escape
  sequences.
- **10.15 PASS** at 60 columns; 300 is trivially fine.
- **10.9/10.10 PASS**, and the summary now covers `check` too (P0-2's fix added
  the line that was missing).

---

## Cross-platform matrix

| Platform | Who | Install | scan | check | run (Docker) | hooks | watch |
|---|---|---|---|---|---|---|---|
| macOS (Apple Silicon) | this audit, 2026-08-16 | PASS (`--local`) | PASS | PASS | PASS (18 tests) | — | — |
| Ubuntu 22.04 native | **unassigned** | CI only | CI only | CI only | CI only | — | — |
| WSL2 + Docker Desktop | **unassigned** | — | — | — | — | — | — |
| Windows 11 native | **unassigned** | CI only | CI only | CI only | — | — | — |
| macOS (Intel) | **unassigned** | — | — | — | — | — | — |

Three of five have no owner, and WSL has no coverage of any kind. That is the
single largest gap in this report and it is a scheduling problem, not an
engineering one — §11 says a full day with four people in a room, and it means
it.

---

## What's genuinely good

**The code-frame renderer.** rustc-quality, with the caret aligned through tabs
and wide CJK characters, and it clamps rather than crashing on bad indices.
This is well past what a one-week project needed and it is the thing that makes
`yeet check` feel like a real tool rather than a script.

**`analyzer/discover.py`.** Depth cap, file cap, inode set, `PermissionError`
tolerance, `.gitignore` spec, foreign-CI detection — and every one of those has
a comment explaining the failure it prevents, not what the line does. Eleven of
§7's fourteen checks were already satisfied before this audit ran. The only
problem with it was that `yeet check` was not calling it.

**The dialect's architecture.** One parser, canonical-only, with the dialect as
a key-rewrite pass immediately after YAML load. That is the design that makes
"a superset, not a replacement" *structurally* true instead of aspirational,
and it is why P0-1 was a fifty-line fix in one function rather than a rewrite.
The `rename_key` helper that preserves `ruamel`'s position data so diagnostics
keep their line numbers is exactly the detail that separates a tool from a
demo.

**`install.sh`'s honesty about capability detection.** Asking "may I use
colour" and "may I use these characters" as two separate questions, with the
comment explaining that a tty with a latin-1 locale is a real configuration, is
better than most shipped installers manage.

**The commit discipline and `undone.md`.** Every session's open items are
written down, in prose, including the ones that are embarrassing — "the
eleventh instance in this repo of a finished thing with no call site" is a team
that is actually looking. Three of the findings in this audit are the same
pattern, and the team had already named the pattern. That is worth more than
any individual fix.

## What I'd cut

**Cut the `--tui` dashboard from the launch.** It is the largest surface with
the least verification: 10.5 (resize) and 10.12 (fuzz) are both open, it needs
an optional dependency, and §10.1 is right that plain mode is what almost
everyone will actually see. Ship it behind the flag it is already behind, say
"experimental" in the README, and spend the day on §11 instead.

**Cut §12.12's GIF from the blocking list, but only just.** It is P2 above and
that is a judgement call I could be argued out of — the audit calls it the
thing that determines whether anyone tries the tool, and it is probably right.
An hour with `asciinema` before the repo goes public is cheap.

**Do not cut §11.** Three of five platforms have no owner. Everything else in
this report is a proxy for "does it work on the user's machine", and one
person on Windows for an hour and one on WSL for an hour answers more than
another day of tests would. That is the last thing standing between this and a
tag.
