<img src="assets/yeet.svg" alt="yeet — run GitHub Actions workflows locally" width="445">

# yeet — run GitHub Actions workflows locally

**yeet** is a local, GitHub Actions-compatible workflow runner. Point it at any
project — cloned from GitHub or created locally — and it finds your workflow
files, tells you if they're written correctly, and runs them in Docker on your
machine. No cloud, no account, no CI minutes.

It even speaks a **dialect of its own** — `vibe`, `the_grind`, `moves`, `drip`,
`tea` — while running canonical GitHub Actions files unchanged. Both spellings,
side by side, in one repo.

```bash
yeet scan bestie          # what is this project, and what flows does it have?
yeet check bestie         # is the .yml written correctly?  (5 validation layers)
yeet run bestie           # run the whole thing on your machine
yeet logs                 # replay the last run
```

That's the whole product in five commands.

## Install

One line, on Linux, macOS, or WSL. It installs into its own isolated
environment and puts `yeet` on your PATH — it never touches your system Python
or any project's virtualenv.

```bash
curl -fsSL https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh | sh
```

Prefer to read it first (you should):

```bash
curl -fsSLO https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh
less install.sh && sh install.sh
```

Or install straight with [pipx](https://pipx.pypa.io):

```bash
pipx install git+https://github.com/TamizhSK/GIST
```

Needs **Python 3.10+** — or nothing at all: where
[uv](https://docs.astral.sh/uv/) is present the installer uses it and lets it
fetch a Python, so a machine with no suitable interpreter still ends up
working. 3.10 rather than 3.11 because that is what Ubuntu 22.04 LTS and its
WSL image ship.

git is optional too — without it the installer pulls a source tarball instead.
Docker is optional — workflows with `cooked_on: local` run in your own shell,
so you can go end-to-end before you ever install a daemon. To remove it:
`yeet-uninstall`.

## Watching a run

`yeet run` streams: one line at a time, safe to pipe, safe to redirect, and it
leaves the whole log in your scrollback. That is the default and it stays the
default.

`yeet run --tui` opens a full-screen dashboard instead — a job/step tree on the
left, the running step's output on the right, `[f]` to follow the live step or
click any step to pin it. Worth it when a matrix has eight legs and the
streaming form interleaves eight jobs into one column.

```
  yeet  ·  CI
 ▼ [OK] test (node 16)  2.4s     │ ── test (node 20) · run tests ──
 ├── [OK] setup  1.1s            │ test 1 ok
 └── > run tests                 │ a warning
 ▼ [FAIL] test (node 18)  2.1s   │
  2/3 jobs  ·  1 flopped  ·  following   [f] follow   [q] quit
```

Needs Textual (`pip install 'yeet[tui]'`). Without it — or into a pipe —
`--tui` says so and falls back to the streaming view, because a runner that
will not run because a display library is missing has failed at its actual job.

## Reproducing GitHub exactly

By default the container gets your working directory bind-mounted, so
**uncommitted edits are what run**. That is the point of a local runner: you
want to test what you are editing.

`yeet run --clean` gives each job an empty workspace instead and lets
`actions/checkout` fill it, exactly as GitHub does. That catches the two things
the bind mount hides — a workflow with no `checkout` step at all, and one that
only passes because of a file you have not committed yet.

## Secrets and variables, imported locally

`yeet secrets import` reads the workflow files, finds every `${{ secrets.X }}`
and `${{ vars.Y }}` they reference, writes those names to `.env`, and fills in
the ones your shell already exports:

```console
$ yeet secrets import
  + AWS_REGION  (variable)
  = NPM_TOKEN   (secret)  ← from your environment
```

Then `yeet run` resolves both. Values read as `secrets.*` are redacted from the
log and from `.yeet/runs/`; `vars.*` are not, so masking works exactly like you
expect. Existing entries are never overwritten — safe to re-run whenever someone
adds a workflow.

## Status

All five subsystems are implemented and wired end to end. `yeet scan → check →
graph → run → logs` works on both the dialect and canonical GitHub Actions
syntax, and the whole suite is green:

```
make check     six gates green (lint · format · imports · types · noprint · test)
pytest         787 fast tests, plus 18 against a live Docker daemon
mypy src       102 source files, strict
lint-imports   2 contracts kept, 0 broken
```

Three OSes in CI (Linux, macOS, Windows), nine real OSS workflows in the
compatibility corpus — all validating clean.

## Start here

- **[`docs/handbook.md`](docs/handbook.md)** — the twenty-minute orientation:
  architecture, every command, how we work. Read this first.
- [`docs/getting-started.md`](docs/getting-started.md) — machine setup and the
  daily dev loop.
- [`docs/architecture.md`](docs/architecture.md) — the design rationale
  (amended by [`docs/adr/0007`](docs/adr/0007-tier-rule-consequences.md)).
- [`docs/understanding-yeet.md`](docs/understanding-yeet.md) — what the thing
  is, with diagrams.
- [`docs/rules.md`](docs/rules.md) — every diagnostic code (generated from
  `core/codes.py`; never hand-edited).
- [`plan.md`](plan.md) — the file-by-file ownership map.
- [`docs/history/`](docs/history/) — the session-by-session build log.

## Development

```bash
git clone https://github.com/TamizhSK/GIST && cd GIST
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
git config core.autocrlf input   # skip this and \r bites you on Thursday

make test    # fast loop, run constantly
make check   # everything CI runs — run before every push
make fix     # repairs what check complains about
```

## Non-goals

See `docs/architecture.md` §9. We say no on purpose.

