# YEET — Launch Readiness Audit Prompt

> Paste this into Claude Code (or any coding agent) at the root of the repo.
> It expects `bootstrap.py`'s tree, `docs/architecture.md`, and `getting-started.md`
> to exist. Delete sections that don't apply yet — a checklist you can't act on
> this week is noise.

---

## ROLE

You are three people at once, and you switch between them explicitly:

**The Senior Software Engineer.** You care about whether the architecture holds
under load, whether the abstractions leak, and whether a change in one module
forces changes in three others. You have shipped CLI tools that thousands of
people installed, and you know the failure modes are never the ones in the
design doc.

**The Senior QA / Test Engineer.** You do not trust "it works on my machine."
You ask *how would I break this*, and then you break it. You care about the
Windows box nobody tested on, the repo with a space in its path, the user whose
terminal is 60 columns wide, the machine with no Docker daemon running. You
write the failing test before you write the fix.

**The Cool Developer.** You care that the thing feels good to use. A tool can be
correct and still be joyless. You know that a great TUI is *legible first,
beautiful second*, that ASCII art which breaks in `cmd.exe` is worse than no ASCII
art, and that "creative" never means "hard to read at 2am when something's on
fire."

When these three disagree, say so out loud in your report and let the engineer
break the tie.

---

## CONTEXT

`yeet` is a local, GitHub Actions-compatible workflow runner built by a team of
four in one week as a training project. It:

- analyses any project (cloned from GitHub or created locally)
- discovers workflow YAML files inside a `workflows/` directory
- validates them across five layers and refuses to run broken ones
- accepts both standard GitHub Actions syntax and a Gen-Z dialect
- executes jobs in local Docker, one container per job, exec per step
- must work on macOS, Windows, Linux, and WSL2

The team intends to publish it publicly on GitHub.

---

## GROUND RULES

1. **Verify, don't assume.** Every item below has a *proof command*. Run it.
   Paste real output. If you cannot run it in this environment, say
   `UNVERIFIABLE HERE` and write the exact command a human must run, plus what
   correct output looks like.
2. **Never report PASS from reading code.** Reading proves intent. Running
   proves behaviour.
3. **Failures get a fix, not a lecture.** For every FAIL, give the smallest diff
   that fixes it.
4. **Prioritise ruthlessly.** This team has days, not months. Every finding is
   tagged `P0` (blocks launch), `P1` (fix this week), or `P2` (post-launch).
   Nothing is P0 unless it breaks install, corrupts a user's files, leaks a
   secret, or makes the tool unusable on one of the three OSes.
5. **Push back on the spec.** Some requirements below are stated as solutions
   when they're really problems. If the requirement as written is the wrong
   engineering answer, say so and propose the right one — §6 is the obvious
   candidate. Do this before implementing it, not after.

---

## THE CHECKLIST

Work through these in order. Sections 1–4 are foundation; 5–9 are user-facing;
10–12 are launch gates.

---

### §1 — Base level: does it even build and import

| # | Check | Proof |
|---|---|---|
| 1.1 | Clean clone installs with no network beyond PyPI | `python -m venv .v && .v/bin/pip install -e ".[dev]"` |
| 1.2 | Every module imports without side effects | `python -c "import importlib,pkgutil,yeet; [importlib.import_module(m.name) for m in pkgutil.walk_packages(yeet.__path__, 'yeet.')]"` |
| 1.3 | No module executes work at import time (no I/O, no Docker connect, no file reads) | grep for module-level calls; import time under 200ms: `python -X importtime -c "import yeet.cli.app" 2>&1 \| tail -5` |
| 1.4 | The tier rule holds — imports only point downhill | `lint-imports` |
| 1.5 | `core/` imports nothing from `yeet.*` | covered by the forbidden-modules contract |
| 1.6 | No `print(` anywhere under `src/` outside `reporting/` | `grep -rn "print(" src/ --include=*.py \| grep -v "src/yeet/reporting/"` — must be empty |
| 1.7 | Type checking is clean | `mypy src` |
| 1.8 | Lint is clean | `ruff check src tests` |
| 1.9 | Test suite passes without Docker | `pytest -m "not docker"` |
| 1.10 | Test suite passes with Docker | `pytest -m docker` |

**Report:** any module doing work at import, any tier violation, any stray print.

---

### §2 — Packaging: does the artifact contain what it claims

This is where CLI tools die silently. The wheel builds, uploads, installs — and
then crashes at runtime because a data file wasn't included.

| # | Check | Proof |
|---|---|---|
| 2.1 | Wheel and sdist build | `python -m build` |
| 2.2 | **Package data is actually in the wheel** — `aliases.yml`, `workflow.schema.json`, `templates/`, `docs/rules.md` | `python -m zipfile -l dist/*.whl \| grep -E "aliases.yml\|schema.json\|templates/"` |
| 2.3 | The sdist can rebuild the wheel (no missing source files) | `pip install dist/*.tar.gz` in a clean venv, then run `yeet --help` |
| 2.4 | Data files are read via `importlib.resources`, **not** `Path(__file__).parent` | `grep -rn "__file__" src/` — every hit must be justified; `__file__` breaks in zipapps and frozen builds |
| 2.5 | Metadata is complete: license, author, homepage, repository, keywords, classifiers, `requires-python` | `python -m twine check dist/*` + read `PKG-INFO` |
| 2.6 | **README renders on PyPI** — PyPI's renderer is stricter than GitHub's | `twine check --strict dist/*`; also `python -m readme_renderer README.md -o /tmp/out.html` |
| 2.7 | README renders on GitHub — relative image paths, no broken anchors | push to a branch and look at it |
| 2.8 | Version is single-sourced (one place defines it) | `grep -rn "0.1.0" --include=*.py --include=*.toml .` — should be one hit |
| 2.9 | Dependency pins have lower bounds and no upper caps except where justified | read `pyproject.toml` |
| 2.10 | Install size is sane (< 5 MB wheel) | `ls -lh dist/*.whl` |
| 2.11 | Installs on Python 3.11, 3.12, 3.13 | CI matrix |
| 2.12 | **TestPyPI dry run before real launch** | `twine upload -r testpypi dist/*` then install from TestPyPI in a clean container |

**P0 if:** package data missing from wheel (2.2), README fails to render (2.6),
or `__file__` used for resource loading (2.4).

---

### §3 — One-line install on all three OSes

The requirement is *one line, three OSes, works*. Design it as **two lines
that each work perfectly** rather than one line that works badly everywhere.

**Recommended shape** — evaluate whether the repo does this:

```bash
# macOS / Linux / WSL
curl -LsSf https://raw.githubusercontent.com/<org>/yeet/main/install.sh | sh
```
```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/<org>/yeet/main/install.ps1 | iex
```

Both scripts should do the same four things: detect or install a Python ≥3.11,
install `uv` (or `pipx`) if absent, `uv tool install yeet`, then verify by
running `yeet --version`.

Audit the installers against this table:

| # | Check | Why it bites |
|---|---|---|
| 3.1 | `set -euo pipefail` in `install.sh`; `$ErrorActionPreference = "Stop"` in `.ps1` | a failed step silently continuing is how users get half-installed tools |
| 3.2 | **Idempotent** — running twice does not duplicate PATH entries or shell-rc lines | grep the rc file for a marker comment before appending |
| 3.3 | Detects arch + OS: darwin/linux/windows × arm64/x86_64, and musl vs glibc | Alpine and Apple Silicon both break naive scripts |
| 3.4 | Detects WSL specifically and says so | user needs to know they're installing into WSL, not Windows |
| 3.5 | Refuses gracefully on Python < 3.11 with the exact upgrade command for that platform | not "python too old" |
| 3.6 | Never requires `sudo`; installs to `~/.local/bin` or `%LOCALAPPDATA%` | a curl-pipe-sudo installer is a red flag on a public repo |
| 3.7 | If the install dir isn't on `PATH`, prints the **exact** export/`$PROFILE` line to add, per shell (bash/zsh/fish/PowerShell) | the #1 "it installed but the command isn't found" complaint |
| 3.8 | Handles paths with spaces (`C:\Users\Tamizh Selvan\`) — quote every variable | classic Windows failure |
| 3.9 | Works behind a corporate proxy — honours `HTTP_PROXY`/`HTTPS_PROXY` | your BMW laptop will hit this |
| 3.10 | `--version` pin supported: `... \| sh -s -- --version 0.2.0` | reproducibility |
| 3.11 | Uninstall path documented and working: `uv tool uninstall yeet` | never ship an installer without one |
| 3.12 | Installer is **also runnable offline from a clone**: `./install.sh --local` | demo insurance |
| 3.13 | PowerShell script works in both Windows PowerShell 5.1 and PowerShell 7 | 5.1 is still the default on many machines |
| 3.14 | ExecutionPolicy problem addressed for 5.1 users | `irm \| iex` fails under Restricted policy — document the one-liner |
| 3.15 | Script is signed/checksummed, or at minimum the README shows how to inspect before running | `curl \| sh` demands you earn trust |

**Proof:** run each installer in a clean container/VM for each OS. Docker gives
you Linux variants free:

```bash
docker run --rm -it ubuntu:22.04 bash -c "apt update && apt install -y curl && curl -LsSf <url> | sh && yeet --version"
docker run --rm -it alpine:3.20 sh -c "apk add curl bash && curl -LsSf <url> | sh && yeet --version"
docker run --rm -it python:3.11-slim bash -c "curl -LsSf <url> | sh && yeet --version"
```
Windows and macOS need real machines — assign them to the teammates who have
them and have each paste terminal output into the PR.

**P0 if:** any of the three OSes fails a clean install, or the installer needs
`sudo`, or PATH guidance is missing (3.7).

---

### §4 — Install TUI: the YEET logo, done responsibly

The requirement is a creative install experience. The engineering constraint is
that install output is the *first* thing a user sees and it must never be the
thing that breaks.

| # | Check |
|---|---|
| 4.1 | ASCII/ANSI logo renders correctly in: Windows Terminal, `cmd.exe`, PowerShell ISE, macOS Terminal, iTerm2, GNOME Terminal, and a bare TTY |
| 4.2 | **Degrades, never garbles.** Three tiers: full colour + box-drawing → plain ASCII + colour → plain ASCII, no colour. Pick the tier by capability detection, not by guessing |
| 4.3 | Honours `NO_COLOR`, `TERM=dumb`, and `--no-color` |
| 4.4 | Detects non-TTY (piped output, CI) and drops to plain text automatically |
| 4.5 | Logo fits in **60 columns** — narrower than you think; users have split panes |
| 4.6 | No emoji in the critical path (Windows `cmd.exe` renders many as boxes). If used, they're decorative and their absence loses no information |
| 4.7 | Unicode box-drawing only when the codepage supports it — check `chcp` on Windows or just set UTF-8 mode |
| 4.8 | Progress indication during install (steps, not a fake spinner that lies about progress) |
| 4.9 | Total install output under one screen on success. Verbose only on `-v` or on failure |
| 4.10 | The logo in `README.md` and the logo in the installer are generated from **one source**, so they can't drift |
| 4.11 | README logo works in GitHub dark mode *and* light mode (`<picture>` with `prefers-color-scheme`, or a transparent PNG that reads on both) |

**Cool Developer note to include in your report:** say whether the logo actually
looks good, and if it doesn't, say why. "Renders without errors" is not the same
as "looks good." Be specific — kerning, weight, whether it reads at a glance.

**Proof:**
```bash
yeet --help | cat            # non-TTY path
NO_COLOR=1 yeet --help
TERM=dumb yeet --help
COLUMNS=60 yeet --help
docker run --rm -it -e TERM=dumb python:3.11-slim ...
```

---

### §5 — Post-install discoverability

The requirement: after installing, the user is told one command that shows
everything `yeet` can do.

| # | Check |
|---|---|
| 5.1 | Installer's last line is a single, copy-pasteable next command — pick **one**, e.g. `yeet help` |
| 5.2 | That command lists every command **with a one-line description and a real example** — not just names |
| 5.3 | Commands are grouped by task (Analyse / Validate / Run / Manage), not alphabetically |
| 5.4 | `yeet` with no args, `yeet help`, `yeet --help`, and `yeet -h` all lead somewhere useful and are consistent with each other |
| 5.5 | `yeet <typo>` suggests the nearest real command (`yeet chekc` → "did you mean `check`?") |
| 5.6 | Every subcommand has `--help` with at least one worked example |
| 5.7 | `yeet explain YEET-E301` works and is discoverable from any diagnostic that prints that code |
| 5.8 | `yeet --version` prints version + Python version + OS + whether Docker was found |
| 5.9 | `yeet doctor` exists — checks Python version, Docker daemon reachability, PATH, WSL status, write permissions on the config dir — and tells the user how to fix each failure |
| 5.10 | Shell completion available for bash/zsh/fish/PowerShell, with an install command |

**5.9 is the highest-value item in this section.** Most support questions your
team will get are answerable by `yeet doctor`.

---

### §6 — Environment isolation: "yeet runs in any project without path errors"

**Engineer, read this before implementing.** The requirement as stated is
"automatically apply its venv." That is the wrong mental model and you should
push back on it in your report.

A venv is a *project's* dependency sandbox. If `yeet` activates its own venv
inside a user's project, you will shadow the project's Python, break their
`node_modules`-equivalent, and produce bug reports nobody can reproduce. Worse,
a workflow step that runs `pip install` would install into yeet's environment.

**The correct answer:** `yeet` is installed as an *isolated application* with a
single executable shim on `PATH`. `uv tool install` and `pipx install` both do
exactly this — private venv, deps fully isolated, entry point symlinked into
`~/.local/bin`. The user never activates anything. `yeet` then works in every
directory on the machine, which is what the requirement actually wanted.

Audit against that:

| # | Check |
|---|---|
| 6.1 | `yeet` runs from any cwd, including a directory with no venv, and one with a *different* venv active |
| 6.2 | Running `yeet` inside a project with an activated venv does **not** import that venv's packages | test with a project that has a conflicting `pyyaml` version |
| 6.3 | Running `yeet` does not modify, create, or activate anything in the user's project except `.yeet/` |
| 6.4 | `.yeet/tmp/`, `.yeet/runs/`, `.yeet/artifacts/`, `.yeet/.secrets` are gitignored — and `yeet init` writes that gitignore |
| 6.5 | Config lives in the OS-correct location via `platformdirs`, never in `~/.yeet` on Windows |
| 6.6 | No dependency on the user's `PYTHONPATH`, `VIRTUAL_ENV`, or `CONDA_PREFIX` — and yeet explicitly unsets these when spawning subprocesses |
| 6.7 | Works when invoked from a git hook, where the environment is minimal and `PATH` is often shorter | this breaks constantly — hooks run with a stripped env |
| 6.8 | Works when invoked by cron/Task Scheduler (no TTY, no shell rc sourced) |
| 6.9 | Absolute path to the yeet executable is resolvable for the git hook shims — don't write `yeet` into a hook, write the resolved path or a `command -v` guard with a clear error |

**Proof:**
```bash
cd /tmp && yeet --version                      # no project, no venv
python -m venv /tmp/other && . /tmp/other/bin/activate && yeet --version
env -i PATH=/usr/bin:/bin $(command -v yeet) --version   # stripped env, like a hook
```

---

### §7 — Workflow discovery: the `workflows/` directory rule

Requirement: workflow YAML must live inside a directory named `workflows` —
`.github/workflows`, `.yeet/workflows`, or any `workflows/` dir.

| # | Check |
|---|---|
| 7.1 | Finds `.github/workflows/*.yml` and `*.yaml` |
| 7.2 | Finds `.yeet/workflows/` (and whatever your native path is — keep it consistent with `yeet init`) |
| 7.3 | Finds a bare `workflows/` at project root |
| 7.4 | Finds nested `workflows/` dirs in a monorepo (`services/api/workflows/`) — decide and **document** whether these are in scope; ambiguity here will cost you demo time |
| 7.5 | **Ignores** a `.yml` outside any `workflows/` dir — but if it looks like a workflow (has `jobs:`/`the_grind:` at top level), emits an INFO diagnostic: "this looks like a workflow but isn't in a `workflows/` directory, so it was skipped" |
| 7.6 | Case sensitivity: `Workflows/` on macOS/Windows vs Linux. Match case-insensitively, warn when the case is non-standard |
| 7.7 | Skips `node_modules`, `.venv`, `vendor`, `target`, `dist` even if they contain a `workflows/` dir |
| 7.8 | Depth cap and file cap enforced; a huge monorepo doesn't hang `yeet scan` |
| 7.9 | Symlink loop doesn't hang | build the fixture: `ln -s .. loop` |
| 7.10 | `PermissionError` on one directory doesn't abort the whole scan |
| 7.11 | Paths with spaces, unicode, and emoji in directory names work |
| 7.12 | Deterministic ordering of discovered files (sort them) — non-deterministic order makes test failures irreproducible |
| 7.13 | Detects `.gitlab-ci.yml` / `Jenkinsfile` / `azure-pipelines.yml` and reports "found, not supported" rather than silently ignoring |
| 7.14 | Zero flows found → helpful message + `yeet init --auto` suggestion, not an error |

**Proof:** build these fixture trees under `tmp_path` and assert on results.
Every one of 7.5–7.12 is a two-line pytest fixture.

---

### §8 — Dialect correctness: Gen-Z ↔ GitHub standard

This is the highest-risk correctness area in the project, because a silent
mistranslation produces a workflow that runs *differently* than the user wrote.

| # | Check |
|---|---|
| 8.1 | **Every real GitHub Actions workflow in `tests/corpus/` parses without error** — pull 10 from popular OSS repos |
| 8.2 | Alias table is **injective**: no two dialect keys map to the same canonical key in a way that could collide at the same nesting level | write a test that asserts this over `aliases.yml` |
| 8.3 | No dialect key collides with a **real** GitHub Actions key. `when:`, `after:`, `stash:` — check every one against the full workflow schema. If a real key is shadowed, that's a P0 correctness bug |
| 8.4 | Aliases are only rewritten **at the key positions where they're valid**, not blindly everywhere. A step named `bet` in `with: {bet: x}` must NOT be rewritten — `with:` values are user data, not schema keys |
| 8.5 | Context-sensitivity: `name` inside `with:` is an input, not a workflow name. Same for `env`, `if` inside action inputs |
| 8.6 | Mixed-dialect files work (some keys standard, some Gen-Z) and emit the style INFO |
| 8.7 | **Round-trip test**: standard file → IR, dialect equivalent → IR, assert the two IRs are identical (ignoring positions). This is the single most valuable test in the suite — write it first |
| 8.8 | Unknown key gets a did-you-mean against *both* tables |
| 8.9 | Event names are handled: `manual:` → `workflow_dispatch`, and the reverse is accepted |
| 8.10 | `on:`-parses-as-`True` handled, plus the Norway problem (`branches: [no]` → `False`) |
| 8.11 | Expression syntax is **not** dialected — `${{ github.sha }}` stays canonical inside both. Confirm no aliasing happens inside `${{ }}` |
| 8.12 | Status vocabulary (`slayed`/`flopped`) is presentation-only and never leaks into exit codes, JSON output, or SARIF |
| 8.13 | `--format json` emits canonical keys, always — machine output must not be slang |
| 8.14 | Document the dialect in a table in the README, generated from `aliases.yml` so it can't drift |

**P0 if 8.3 or 8.4 fails.** Those produce workflows that silently do the wrong
thing, which is worse than crashing.

---

### §9 — Real-world workflow features via local Docker

Requirement: handle `checkout@v4`, GHCR, Docker Hub, and similar real usage.

| # | Check |
|---|---|
| 9.1 | `actions/checkout@v4` resolves and works — including on a repo with submodules and one with no remote |
| 9.2 | Action resolution is cached under the user cache dir and works **offline** on second run |
| 9.3 | GitHub API rate limit (60/hr unauthenticated) is handled with a clear message, and `GITHUB_TOKEN` is used when present |
| 9.4 | Docker Hub images pull; anonymous rate limit produces a *comprehensible* error, not a stack trace |
| 9.5 | GHCR images pull; private ones give an actionable auth message |
| 9.6 | Registry auth reuses the user's existing `~/.docker/config.json` — never ask for credentials yourself |
| 9.7 | `docker.from_env()` failure (daemon not running) → exit code 3 and a **platform-specific** fix message (Docker Desktop / systemctl / WSL integration toggle) |
| 9.8 | Project `Dockerfile` auto-detected, built, and cached by content hash; second run is instant |
| 9.9 | Build failure surfaces the actual Docker build log, not a wrapped exception |
| 9.10 | Bind mount works with spaces and unicode in the host path, on all OSes |
| 9.11 | Files created in the container are owned by the host user on Linux/WSL — `git status` is clean after a run |
| 9.12 | `Ctrl-C` mid-run stops and removes every container. No orphans | `docker ps -a` after: must be clean |
| 9.13 | Long-running step can be killed; timeout enforced |
| 9.14 | Step scripts are written LF-only regardless of host OS |
| 9.15 | Secrets are masked in stdout, stderr, **and** the persisted JSONL log, including base64 and URL-encoded variants |
| 9.16 | Large log output (100k lines) doesn't blow memory or lock the TUI |
| 9.17 | Unsupported real-world keys (`services:`, `container:`, `concurrency:`, reusable workflows) produce a clear "not supported" diagnostic rather than being silently ignored |

**9.17 is a correctness issue, not a scope issue.** Silently ignoring
`concurrency:` means the user's workflow ran differently than they wrote it.

---

### §10 — Run TUI and logging legibility

Requirement: a Claude Code-quality TUI, *and* fully legible output without it.

The Cool Developer takes the lead here; the QA engineer keeps them honest.

| # | Check |
|---|---|
| 10.1 | **Plain mode is the default and is genuinely good** — not a degraded fallback. Most CI and most piped usage will see this |
| 10.2 | Every line in plain mode is self-contained: timestamp, job, step, stream. Someone reading a scrollback with no context can follow it |
| 10.3 | Errors are visually distinct without relying on colour alone (prefix, symbol, indentation) — colourblind users and `NO_COLOR` both matter |
| 10.4 | Live TUI: per-job status, per-step timing, current step highlighted, spinner only where progress is genuinely unknown |
| 10.5 | TUI handles terminal resize mid-run without corrupting |
| 10.6 | TUI never hides the error. When a step fails, the failing output is **visible without scrolling back** — surface the last N lines of the failed step at the end |
| 10.7 | Interleaved output from parallel jobs is attributed correctly and never garbled |
| 10.8 | `::group::` collapses in TUI mode and prints as a labelled section in plain mode |
| 10.9 | Final summary is scannable in under two seconds: what ran, what failed, how long, exit code |
| 10.10 | The failure summary tells the user *what to do next*, not just what broke |
| 10.11 | Diagnostics use the rustc/eslint code-frame format, with the caret aligned correctly even with tabs and wide CJK characters in the source line |
| 10.12 | **The renderer never crashes.** Bad line/col indices clamp; the whole render is wrapped and falls back to `str(diagnostic)` | fuzz it: random positions, empty files, 10k-char lines |
| 10.13 | Output is identical in content (not styling) between TUI and plain mode — no information exists only in one |
| 10.14 | Redirecting to a file produces clean text with no escape codes | `yeet run > out.txt 2>&1 && file out.txt` |
| 10.15 | Works at 60 columns and at 300 columns |

**10.6 and 10.12 are the two that will actually bite you in the demo.**

---

### §11 — Cross-platform matrix

Every item below, on every platform. Assign one platform per teammate; each
pastes real output into the tracking issue.

| Platform | Who | Install | scan | check | run (Docker) | hooks | watch |
|---|---|---|---|---|---|---|---|
| Ubuntu 22.04 native | | | | | | | |
| WSL2 (Ubuntu) + Docker Desktop | | | | | | | |
| Windows 11 native + Docker Desktop | | | | | | | |
| macOS (Apple Silicon) | | | | | | | |
| macOS (Intel) — if available | | | | | | | |

Platform-specific traps to verify explicitly:

- WSL: repo under `/mnt/c/` → slow-path warning fires; repo under `~/` → fast
- WSL: Docker Desktop integration off → clear, specific error message
- Windows: path with a space, path > 260 chars, `cmd.exe` vs PowerShell vs Git Bash
- Windows: git hooks execute (they're `sh` scripts under Git for Windows)
- macOS: Apple Silicon pulls `arm64` images; `linux/amd64` images emulate with a warning about speed
- macOS: Gatekeeper doesn't block anything the installer writes
- All: filesystem case sensitivity difference between host and Linux container

---

### §12 — Public launch gate

Before the repo goes public:

| # | Check |
|---|---|
| 12.1 | `LICENSE` present (MIT or Apache-2.0) and referenced in `pyproject.toml` |
| 12.2 | **No secrets in history** — not just the working tree | `gitleaks detect --no-git=false` or `trufflehog git file://.` |
| 12.3 | No internal BMW identifiers, hostnames, registry URLs, ticket IDs, or employee emails anywhere in code, comments, commit messages, or fixtures |
| 12.4 | The README states this is a personal/training project, not a BMW product — protects you and them |
| 12.5 | `act` and `actions/runner` credited explicitly in the README |
| 12.6 | Non-goals section in the README (§9 of the architecture doc) |
| 12.7 | `SECURITY.md` with a disclosure email |
| 12.8 | `CONTRIBUTING.md` with the dev setup from `getting-started.md` |
| 12.9 | `CODE_OF_CONDUCT.md` |
| 12.10 | CI badge is green and points at the real workflow |
| 12.11 | Issue templates (bug/feature) that ask for `yeet doctor` output |
| 12.12 | A 30-second asciinema/GIF in the README showing `scan → check → run`. This is what determines whether anyone tries it |
| 12.13 | Tag `v0.1.0`, write release notes, attach the built wheel + sdist |
| 12.14 | The one-line install command in the README is **the exact string you tested**, pointing at a URL that exists |
| 12.15 | Someone outside the team follows the README from scratch on a clean machine and succeeds without asking questions. If they ask a question, that's a README bug — fix it and repeat |

**12.15 is the real gate.** Everything else is a proxy for it.

---

## DELIVERABLE

Produce `AUDIT.md` at the repo root with this structure:

```markdown
# YEET Launch Readiness Audit — <date>

## Verdict
SHIP / SHIP WITH CAVEATS / DO NOT SHIP — one paragraph, no hedging.

## P0 — blocks launch
| # | Finding | Section | Evidence | Fix | Est |

## P1 — fix this week
(same table)

## P2 — post-launch
(same table)

## Section results
§1 …  PASS 8/10 · FAIL 2 · UNVERIFIABLE 0
(one line per section, then details for every non-PASS)

## Cross-platform matrix
(the filled table from §11, with who ran what and when)

## What's genuinely good
Be specific and honest. If the dialect is clever, say why. If the code-frame
renderer is better than it needed to be, say so. A report that's only negative
gets ignored, and this team has one week — morale is a real input.

## What I'd cut
Scope you should drop to make Friday. Name it explicitly. Somebody has to.
```

Then open one GitHub issue per P0 and P1 finding, with the proof command in the
body and the section number as a label.

---

## HOW TO WORK THROUGH THIS

1. Run §1 first and fix everything before continuing. A broken import makes
   every later result meaningless.
2. Then §2 and §3 together — packaging and install are one problem.
3. §7 and §8 are your correctness core. Spend real time there. If you only
   have one day, spend it here: 8.3, 8.4, and 8.7 in particular.
4. §4, §5, §10 are polish. Do them *after* correctness, but don't skip them —
   they're what makes the difference between a project people star and one
   they close.
5. §11 is a full day with four people in a room. Schedule it, don't hope for it.
6. §12 is the last two hours before you make the repo public.

Where a check needs a test that doesn't exist, **write the test** rather than
verifying manually. A manual check passes once; a test passes forever. Prefer
adding to `tests/invalid/` and `tests/corpus/` over writing new bespoke tests —
those two directories are table-driven and cost almost nothing per case.

Start now. Report §1 before moving on.