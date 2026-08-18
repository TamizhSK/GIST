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

## How it works

`yeet run` is the full pipeline, and **every other command is a shorter prefix
of it** — `scan` stops after analysis, `check` after validation, `graph` after
planning. The one idea that makes it a product rather than a script is the
**gate**: a workflow file with errors never creates a container.

```
 yeet run — the whole product in one picture (each command is a prefix of it)

  project dir            workflow .yml         IR (dataclasses)       side effects
┌─────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ 1. ANALYZER     │──▶│ 2. VALIDATE      │──▶│ 4. PLAN          │──▶│ 5. EXECUTE       │
│  find_root()    │   │  (the GATE)      │   │  matrix.py →     │   │  one container   │
│  discover()     │   │  5 layers,       │   │  topo_waves →    │   │  per job, one    │
│  fingerprint()  │   │  errors → exit 2 │   │  ExecutionPlan   │   │  exec per step   │
└─────────────────┘   └────────┬─────────┘   └──────────────────┘   └────────┬─────────┘
                               │                                             │
                               ▼                                             ▼
                    ┌──────────────────┐                         ┌──────────────────┐
                    │ 3. IR BUILDER    │                         │ 6. OUTPUT        │
                    │  parser +        │                         │  RunConsole      │
                    │  aliases +       │                         │  (live tree)     │
                    │  builder → IR    │                         │  RunStore (JSONL)│
                    └──────────────────┘                         └──────────────────┘
```

Stages 2 and 3 together are the validator: parse the file, normalise any dialect
keys to canonical GitHub Actions, build the internal representation, then run
five check layers over it.

```
  THE VALIDATION PIPELINE — layer 4 prints opinions, only 0–3 can stop the run

  layer 0  bytes           E001 unreadable · E002 empty · E005 tabs · W006 CRLF
  layer 1  YAML            ruamel round-trip · E102 duplicate keys · W105 on:→True
  ── dialect pass          parser/aliases.py::normalize()  → canonical keys
  layer 2  schema          jsonschema against the canonical form · did-you-mean
  ── builder               parser/builder.py → Workflow IR (positions set AS built)
  layer 3  semantics       E301 needs→unknown job · E302 cycles · expressions
  layer 4  lint            W402 moving refs · W404 hardcoded secrets · W409 host paths

  any error in layers 0–3?  ──yes──▶  render rustc-style code frames · exit 2
                                       NO CONTAINER WAS EVER CREATED
```

If the file is clean, the planner turns the IR into waves of runnable jobs, the
executor runs them, and every log line flows through a single fan-out: a live
tree on your terminal **and** a JSONL file that `yeet logs` replays later.

## The architecture — one rule

The whole codebase is organised into eight tiers, and the rule is enforced by
`lint-imports` on every push: **imports only ever point downhill.** A module may
import from lower tiers, never from a higher one and never from a sibling on the
same line.

```
  tier 7   cli/            the only tier that may import anything
  tier 6   triggers/       file watcher · git hooks
  tier 5   executor/ · storage/ · secrets/      siblings — MAY NOT import each other
  tier 4   planner/        matrix · DAG · waves
  tier 3   validation/     the five-layer gate
  tier 2   parser/ · analyzer/ · actions/       siblings — actions resolves, never runs
  tier 1   expressions/ · reporting/            siblings
  tier 0   core/           imports nothing from us. Ever. (closed)
```

When the rule blocks an import, the fix is always the same move: **push the pure
part down into `core/` and leave the policy up top.** That single trick resolved
every conflict it caused — `core/masking.py` (a pure `Masker` the executor uses),
`core/events.py` (a `LogSink` protocol so the executor never touches `storage/`),
`core/graph.py` (cycle detection shared by validation and planning). `core/` is
closed: `ir.py` and `diagnostics.py` are frozen, and adding a sixth file there
takes the whole team.

## Install

One line per platform. Each installs into its own isolated environment and puts
`yeet` on your PATH — it never touches your system Python or any project's
virtualenv.

**Linux, macOS, WSL**

```bash
curl -fsSL https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex
```

If that is refused, your execution policy is doing its job. For one command:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex"
```

New terminals have `yeet` on PATH from then on. To use it in the terminal you
ran the installer in, source the env file it leaves behind — no process can put
something on the PATH of the shell that started it, so this is the one manual
step, and it is one line:

```bash
. "$HOME/.local/share/yeet/env"     # fish: source ~/.local/share/yeet/env.fish
```

Then, before anything else:

```bash
yeet doctor     # is this machine set up to run a workflow, and if not, what to fix
```

Prefer to read the script first (you should):

```bash
curl -fsSLO https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh
less install.sh && sh install.sh
```

Run from a clone, the installer installs **that clone** — no flag, no network,
and no way to accidentally install `main` over the branch you are editing:

```bash
./install.sh                  # PowerShell: .\install.ps1
```

Pin a published version instead, from anywhere:

```bash
curl -fsSL https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh | sh -s -- --version v0.2
./install.sh --version main   # from inside a clone: fetch, don't use the clone
```

Or install straight with [pipx](https://pipx.pypa.io) or
[uv](https://docs.astral.sh/uv/):

```bash
pipx install git+https://github.com/TamizhSK/GIST
uv tool install git+https://github.com/TamizhSK/GIST
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

Neither installer needs `sudo` or an elevated prompt. On POSIX it writes to
`~/.local/share/yeet` and `~/.local/bin`; on Windows, `%LOCALAPPDATA%\yeet`.

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

The layout follows the window. The output pane is never given the smaller half,
and under 72 columns the two panes stop competing for the same row and stack —
a tree squeezed to 25 columns and a log squeezed to 18 are two panes you cannot
read instead of one you can. Resizing mid-run re-fits.

The dashboard stays up when the run ends — it is a thing you watch, and the
alternate screen is discarded on exit, so it waits for `q` rather than taking
the run away with it. The summary is printed to your scrollback afterwards
either way.

Needs Textual, which both installers put in yeet's own virtualenv for you. If
you installed with bare `pip`/`pipx`/`uv`, ask for it: `pip install 'yeet[tui]'`.
Without it — or into a pipe — `--tui` says so and falls back to the streaming
view, because a runner that will not run because a display library is missing
has failed at its actual job.

## Reproducing GitHub exactly

By default the container gets your working directory bind-mounted, so
**uncommitted edits are what run**. That is the point of a local runner: you
want to test what you are editing.

`yeet run --clean` gives each job an empty workspace instead and lets
`actions/checkout` fill it, exactly as GitHub does. That catches the two things
the bind mount hides — a workflow with no `checkout` step at all, and one that
only passes because of a file you have not committed yet. (A workflow with no
`checkout` anywhere is called out on every normal run too, since it works here
for a reason that will not exist in CI.)

### Actions from the marketplace

`uses: owner/repo@ref` is fetched and, if it is a composite action, inlined and
run. Any ref works, including the full commit SHA that
[`YEET-W402`](docs/rules.md#yeet-w402) asks you to pin to.

The fetch happens once per ref and says so on the step's own line, because a
`uses:` line reaching the network is worth seeing. It is cached under your
platform cache directory — forever for a SHA or an exact tag, and for a day for
a moving `@v4`, which is re-pointed by its author at every minor release.

```console
$ yeet run --offline     # never fetch; use what is already cached
$ yeet prune --actions   # empty that cache
```

`YEET_OFFLINE=1` does the same as the flag, and `YEET_ACTION_TTL` (seconds)
changes how long a moving ref is reused.

`actions/checkout`, `cache`, `upload-artifact` and `download-artifact` are
built in rather than fetched — on GitHub they talk to a hosted service that
does not exist here, so what a local runner owes you is their behaviour, not
their JavaScript. Docker and node actions are still skipped, now with a message
naming which of the two it was.

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

All five stages are implemented and wired end to end. `yeet scan → check →
graph → run → logs` works on both the dialect and canonical GitHub Actions
syntax, and the whole suite is green:

```
make check     six gates green (lint · format · imports · types · noprint · test)
pytest         985 fast tests, plus 18 against a live Docker daemon
mypy src       107 source files, strict
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
- [`docs/plan.md`](docs/plan.md) — the file-by-file ownership map.
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

We say no on purpose. The full list is in
[`docs/architecture.md`](docs/architecture.md) §9; the ones people ask about
most:

- **Not a GitHub Actions replacement.** It runs your workflows locally so the
  push is the second time you find out, not the first. GitHub is still the
  thing that gates a merge.
- **No hosted anything.** No service, no artifact server, no accounts. An
  artifact is a file in `.yeet/artifacts/`, and `upload-artifact` deliberately
  emits no `artifact-url`, because a plausible-looking dead link is worse than
  a missing field.
- **No sandbox around `runs-on: local`.** Those steps run in your shell, on
  your machine, as you. That is the point of them, and it is why the default
  is a container.
- **Not every key.** `services:`, `concurrency:` and reusable workflows are
  reported as unsupported rather than ignored — a workflow that ran
  differently than you wrote it is worse than one that refused.
- **Not a linter for other CI systems.** A `.gitlab-ci.yml` is recognised and
  named, and then left alone.

## Prior art

[`nektos/act`](https://github.com/nektos/act) got here first and is the
reference for what "run Actions locally" means; several of its hard-won
behaviours — the runner-label to image mapping, the shape of the container
lifecycle — are the obvious answers because act found them.
[`actions/runner`](https://github.com/actions/runner) is the real thing, and it
is the authority every fidelity question here was settled against.

## About this project

This is a **personal training project**, built by four people in a week. It is
not a product of, affiliated with, or endorsed by any employer of any
contributor, and nothing in this repository is anyone's work product but ours.
Use it accordingly: it is pre-1.0, the CLI surface can still change, and the
[non-goals](#non-goals) above are real limits rather than a roadmap.

## License

[MIT](LICENSE).

