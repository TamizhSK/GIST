# Building Your Own Local GitHub Actions Runner

**Working codename used throughout:** `yeet` (rename freely — the CLI name is a one-line constant)

> ### Amended by ADR 0007 — read this before you follow §3.4, §3.10 or §6
>
> This document's reasoning still stands; four of its *placements* do not. The
> `import-linter` contract in `pyproject.toml` makes same-tier siblings
> **independent**, which forbids three imports this guide implies, and one more
> is an upward import. Verified, not assumed — see
> [`adr/0007`](adr/0007-tier-rule-consequences.md).
>
> | This guide says | Actually |
> |---|---|
> | masking lives in `secrets/` (§5, §6 Dev D) | pure `Masker` is in **`core/masking.py`**; `secrets/store.py` keeps only loading and decryption. `executor` may not import `secrets`. |
> | the executor writes run logs via `storage/` (§5) | the executor emits to a **`core.events.LogSink`** Protocol; `storage.runs` implements it. `executor` may not import `storage`. |
> | `actions/` sits beside the executor (§3.7) | `actions/` is **tier 2**, beside `parser/`. It resolves `uses:` into IR and executes nothing; the executor consumes the result. |
> | "`planner/graph.py::find_cycle()` does double duty" (§3.4) | the walk is in **`core/graph.py`**. Validation is tier 3 and the planner is tier 4, so Layer 3 cannot call into the planner. `planner/graph.py` is a thin adapter. |
>
> Everything else — the pipeline, the five validation layers, the diagnostic
> codes, one-container-per-job, the cross-platform checklist — is unchanged.
> `plan.md` is the file-by-file assignment; this is the *why*.

---

## 0. Read this first: the one decision that makes or breaks the week

You have ~1 week and 4 people. The single highest-leverage thing you can do is
**define the internal representation (IR) on Day 0 and freeze it.** Everything
else — parser, scheduler, Docker executor, logger — talks only to the IR, never
to each other. That's what lets four people write code in parallel without
blocking.

```
  any project dir        raw YAML/JSON        IR (dataclasses)         side effects
┌────────────────┐   ┌────────────────┐   ┌──────────────────┐   ┌────────────────┐
│ 1. ANALYZER    │──▶│ 2. PARSER +    │──▶│ Workflow → Jobs  │──▶│ 5. EXECUTOR    │
│ detect root,   │   │    ALIAS LAYER │   │ → Steps          │   │ Docker / local │
│ discover flows,│   │                │   │ + Contexts       │   │                │
│ fingerprint    │   └────────────────┘   └──────────────────┘   └────────────────┘
└────────────────┘           │                     │                     │
                             ▼                     ▼                     ▼
                    ┌────────────────┐   ┌──────────────────┐   ┌────────────────┐
                    │ 3. VALIDATOR   │   │ 4. SCHEDULER     │   │ Log stream     │
                    │ 5 layers →     │   │ matrix + DAG     │   │ + JSONL store  │
                    │ Diagnostics    │   └──────────────────┘   └────────────────┘
                    └────────────────┘
                             │
                             ▼
                   pretty report / JSON / SARIF
                   ↳ hard-stop before execution on any ERROR
```

**Nothing executes until the Validator returns zero errors.** That gate is the
whole reason your tool is usable on arbitrary repos you didn't write.

If you get this wrong you will spend Thursday night merging conflicts instead
of demoing.

---

## 1. Prior art — study it, don't copy it

| Project | What to learn from it |
|---|---|
| `nektos/act` (Go) | This is almost certainly the "already developed architecture" you were pointed at. Read its `pkg/runner/` and `pkg/model/` folders. Its container-reuse-per-job trick is the core insight. |
| `actions/runner` (C#, GitHub's real one) | Read `docs/adrs/` — architecture decision records explaining *why* things are the way they are. Great material for your presentation. |
| GitHub Actions docs — "Workflow syntax" | Your schema reference. Bookmark the contexts + expressions pages. |
| `docker/docker-py` or `moby/moby` API docs | The container API you'll actually call. |

**Say this out loud in your demo:** "We studied `act`'s architecture, re-derived
it, and extended it with X." Trainers reward honest attribution far more than
they reward pretending.

---

## 2. Language & stack choice

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Python 3.11+** | Fastest to build. `PyYAML`, `docker`, `typer`, `rich`, `jsonschema`, `watchdog` all mature. Great TUI output. | Distribution needs Python on target machine (`pipx install`). | ✅ **Pick this** for a 1-week deadline |
| Go | Single static binary, true cross-platform distribution, what `act` uses | You'll spend 2 of your 7 days fighting the language | Only if 2+ of you already write Go daily |
| Node/TypeScript | Good if you want to support JS actions natively | YAML + process handling is clunkier | Second choice |

**Recommended Python stack:**

```
typer         # CLI
pydantic v2   # IR models + validation
ruamel.yaml   # parsing — KEEPS line/column info (see §3.10). Prefer over PyYAML.
PyYAML        # optional fast path (use yaml.safe_load ONLY, never yaml.load)
jsonschema    # workflow schema validation w/ good error messages
pathspec      # .gitignore-style exclusion when walking project trees
identify      # file-type detection helper for project fingerprinting
docker        # Docker Engine API SDK
rich          # colored grouped log output, live status tree
watchdog      # filesystem triggers
lark          # expression grammar (or hand-roll a Pratt parser)
keyring       # OS-native secret store (optional, nice touch)
pytest        # golden-file tests
```

---

## 3. System architecture — the ten subsystems

> Read §3.9 and §3.10 first if you're implementing the pipeline in order — the
> Analyzer runs *before* the parser and the Validator gates everything after it.

### 3.1 CLI (entrypoint)

```
yeet scan [dir]              # analyse a project: type, flows found, health report
yeet check [dir] [--strict]  # full 5-layer validation, no execution   ← key deliverable
yeet check --format json     # machine-readable diagnostics (also: --format sarif)
yeet explain YEET-E203       # print docs for one diagnostic code
yeet init [--auto]           # scaffold a flow (--auto = generate from detected stack)
yeet run [flow] [--job X]    # run once (validates first, refuses on error)
yeet run --event push        # simulate a trigger
yeet watch [dir]             # daemon: watch for new/changed projects
yeet hooks install           # write git hooks into .git/hooks
yeet secrets set KEY         # store a secret locally
yeet logs [run-id]           # replay a past run
yeet graph                   # print the job DAG (great demo moment)
```

Exit codes matter: `0` slay, `1` job failed, `2` bad workflow file, `3` no
Docker daemon. Your trainer may pipe it into something.

### 3.2 Parser + Gen-Z alias layer

This is where your differentiator lives, and the architecture trick is:
**one canonical parser, one data-driven alias table.**

Do **not** write two parsers. Write one, and normalize keys through a lookup
table loaded from `aliases.yml`:

```yaml
# aliases.yml — bidirectional key mapping
vibe:            name
when:            "on"
the_grind:       jobs
cooked_on:       runs-on
moves:           steps
bet:             run
yoink:           uses
after:           needs
only_if:         if
drip:            env
tea:             secrets
multiverse:      matrix
loot:            artifacts
stash:           cache
patience:        timeout-minutes
delulu:          continue-on-error
squad:           strategy
```

Then a `normalize(node)` function walks the parsed tree and rewrites keys.
Result: **real GitHub Actions workflow files still run unchanged.** That
compatibility claim is worth more marks than the slang itself.

Example workflow in your dialect:

```yaml
vibe: ship it fr fr

when:
  push:
    branches: [main]
  manual: {}          # ← your alias for workflow_dispatch

drip:
  NODE_ENV: production

the_grind:
  build:
    cooked_on: ubuntu-latest
    squad:
      multiverse:
        node: [18, 20, 22]
    moves:
      - vibe: pull up the code
        yoink: ./.yeet/actions/checkout

      - vibe: install deps
        bet: npm ci

      - vibe: run tests
        bet: npm test
        delulu: true          # continue-on-error

  deploy:
    after: [build]            # needs
    cooked_on: ubuntu-latest
    only_if: ${{ github.ref == 'refs/heads/main' }}
    moves:
      - bet: echo "shipping ${{ github.sha }}" && ./deploy.sh
```

Status vocabulary for output: `slayed` / `flopped` / `mid` (partial) /
`skipped (not the vibe)` / `cooked` (running).

**Validation:** write a JSON Schema for the canonical form. Run
`normalize()` → `jsonschema.validate()`. Emit errors with file, line, column
and a *did-you-mean* suggestion using `difflib.get_close_matches` against both
canonical keys and aliases. Good error messages are 20% of perceived quality.

### 3.3 Expression engine — `${{ ... }}`

This is the subsystem people underestimate. You need:

**Contexts** (dicts injected at eval time):
- `github` — `sha`, `ref`, `ref_name`, `repository`, `actor`, `event_name`, `workspace`, `run_id`, `run_number`
- `env`, `job`, `steps`, `runner`, `matrix`, `needs`, `secrets`, `inputs`, `vars`

**Operators:** `==` `!=` `<` `>` `<=` `>=` `&&` `||` `!` `()` and property/index access `a.b`, `a['b']`, `a[0]`, plus the `*` splat.

**Functions:** `contains()`, `startsWith()`, `endsWith()`, `format()`, `join()`, `toJSON()`, `fromJSON()`, `hashFiles()`, and the status checks `success()`, `failure()`, `always()`, `cancelled()`.

**Loose-equality quirk to replicate:** GitHub coerces types (`'1' == 1` is
true, `'' == 0` is true). Mimic it or explicitly document that you don't —
either is fine, silently differing is not.

Implementation: define a small grammar in `lark`, or hand-roll a
tokenizer + Pratt parser (~250 lines). **Never `eval()`.** That's an
injection hole and your trainer will find it.

Where expressions get evaluated matters:
- `if:` — evaluated *without* `${{ }}` wrapper allowed (GitHub permits bare)
- `run:` — string-interpolated before the script is written to disk
- `env:`, `with:` — interpolated at step start
- Job-level `if:`, `needs` results — evaluated before the job is scheduled

### 3.4 Scheduler (job DAG)

```python
# 1. Expand matrices → concrete job instances
# 2. Build dependency graph from `needs`
# 3. Detect cycles → fail fast with the cycle printed
# 4. Topological sort into waves
# 5. Run each wave with a bounded thread/process pool (--jobs N, default = cpu_count)
# 6. Propagate results into the `needs` context for downstream jobs
```

Rules to honor:
- A job whose `needs` failed is **skipped**, unless its `if:` uses `always()` or `failure()`
- `strategy.fail-fast: true` (default) cancels sibling matrix legs on first failure
- `strategy.max-parallel` bounds matrix concurrency
- `matrix.include` adds legs / extends existing ones; `matrix.exclude` removes them — implement `exclude` *after* `include`

`yeet graph` should render this as an ASCII tree. It's a 30-line function that
makes the demo look serious.

### 3.5 Execution backend (the Docker part)

**Core insight — one container per job, `exec` per step.**

Naive implementations run each step as `docker run`, which loses all state
between steps (cd, env vars, installed packages). Instead:

```python
container = client.containers.create(
    image=resolved_image,
    command=["tail", "-f", "/dev/null"],   # keep-alive
    working_dir="/workspace",
    volumes={host_repo_path: {"bind": "/workspace", "mode": "rw"}},
    environment=base_env,
    user=f"{os.getuid()}:{os.getgid()}" if is_linux() else None,
    network="bridge",
    auto_remove=False,
)
container.start()

for step in job.steps:
    write_script(step)                       # to .yeet/tmp/step-N.sh, LF endings
    exit_code, stream = container.exec_run(
        cmd=["bash", "-e", "/workspace/.yeet/tmp/step-N.sh"],
        environment=step_env,
        stream=True, demux=True,
    )
    stream_logs(stream)
    read_back_state_files()                  # see 3.6

container.stop(); container.remove()
```

**Image resolution:**

| `cooked_on:` value | Resolves to |
|---|---|
| `ubuntu-latest` / `ubuntu-22.04` | your prebuilt base image, e.g. `yeet/ubuntu:22.04` |
| `node:20` (any `image:tag`) | pulled directly |
| `./Dockerfile` or `dockerfile: ./path` | `docker build` → tag `yeet-local/<repo>-<sha256(dockerfile)[:12]>` |
| `local` / `native` | no container; run in host shell (bash / pwsh) |

For the Dockerfile case: hash the Dockerfile + build context file list, use it
as the tag, and skip the build if the tag already exists. That's your build
cache and it's ~15 lines.

**Auto-detection** (your requirement about "using the Dockerfile in the project
directory"): if `cooked_on` is absent and a `Dockerfile` exists at repo root,
default to building it. Print a clear line: `no cooked_on set → found
./Dockerfile → building`.

**Base image contents.** `ubuntu:22.04` is empty — no git, no node, no curl.
Either build your own base image once and push to Docker Hub / a local
registry, or run a bootstrap step. Recommended `Dockerfile.base`:

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates jq unzip build-essential python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs
```

### 3.6 State passing between steps (do not skip this)

Each `run:` step is a separate process. GitHub solves this with **files the
step appends to, which the runner reads back afterwards.** Replicate exactly:

| Env var | Purpose | Format |
|---|---|---|
| `GITHUB_ENV` | export env vars to later steps | `KEY=value` per line; heredoc form for multiline |
| `GITHUB_OUTPUT` | step outputs → `steps.<id>.outputs.<k>` | `key=value` |
| `GITHUB_PATH` | prepend to `PATH` | one path per line |
| `GITHUB_STEP_SUMMARY` | markdown summary | markdown |
| `GITHUB_STATE` | pre/post action state | `key=value` |

Also alias these as `YEET_ENV`, `YEET_OUTPUT`, etc. so both work.

**Workflow commands** — parse stdout for `::` directives:
```
::group::Installing
::endgroup::
::error file=app.js,line=10::Something broke
::warning::heads up
::notice::fyi
::add-mask::supersecret
::debug::verbose thing
```
`::group::` → collapsible section in your `rich` output. `::add-mask::` →
add to the mask set immediately. This is genuinely how the real thing works
and demoing it lands well.

### 3.7 Actions support (`yoink:` / `uses:`)

Tier this by cost. Don't attempt full parity in a week.

| Tier | Type | Effort | Do it? |
|---|---|---|---|
| 1 | **Local composite** — `./.yeet/actions/foo` with `action.yml` containing `runs.using: composite` + steps | Low | ✅ Day 3 |
| 2 | **Docker action** — `runs.using: docker`, `image: Dockerfile` | Medium | ✅ Day 4 |
| 3 | **JS action** — `runs.using: node20`, `main: dist/index.js` | Medium | ✅ Day 5 if time |
| 4 | Remote `actions/checkout@v4` from GitHub | Medium | ⚠️ Stretch |
| 5 | `@actions/toolkit` full API surface | High | ❌ Out of scope, say so |

**Input convention:** `with: { foo: bar }` becomes env var `INPUT_FOO=bar`
(uppercase, `-` and spaces → `_`). Defaults come from `action.yml`'s
`inputs.<name>.default`. Missing `required: true` input → hard error before
the step runs.

**Remote resolution** (Tier 4): `owner/repo@ref` → shallow
`git clone --depth 1 --branch <ref>` into `~/.yeet/actions/owner/repo/ref/`,
cached by ref. Most popular actions ship a bundled `dist/index.js`, so if node
is in the container they just work.

Ship your own `./.yeet/actions/checkout` composite (it's basically
`git clone` / `cp -r`) so your demo workflow has zero external dependencies.

### 3.8 Triggers — "runs whenever we upload or create a project"

Three mechanisms, implement 1 and 2, mention 3:

**1. Watcher daemon** (`yeet watch ~/projects`)
- `watchdog` observer on the directory
- On new subdirectory OR change under an existing project: debounce 500ms,
  check for `.yeet/flows/*.yml` or `.github/workflows/*.yml`, then dispatch
  `event_name=push` (or a custom `on: created`)
- Maintain a per-project lock so a run in progress isn't re-triggered
- Ignore `.git/`, `node_modules/`, `target/`, `.yeet/tmp/`

**2. Git hooks** (`yeet hooks install`)
- Write `.git/hooks/post-commit` and `pre-push` shell shims that call
  `yeet run --event push --sha $(git rev-parse HEAD)`
- Make them executable (`0o755`), and on Windows they must be shebang-`sh`
  scripts (Git for Windows ships bash — this works)
- Non-blocking by default; add `--blocking` to fail the push on red

**3. Local webhook receiver** (stretch)
- `yeet serve --port 8787` → tiny HTTP server that accepts GitHub webhook JSON
- Point a tunnel (ngrok/cloudflared) at it and you can trigger from a *real*
  GitHub push. This is the single most impressive demo moment if you have time.
- Verify `X-Hub-Signature-256` HMAC if you build it.

---

### 3.9 Project Analyzer — "work on any repo, pulled or freshly created"

This subsystem runs **before** the parser. Its job: given an arbitrary
directory, figure out (a) where the project root is, (b) which files are
workflows, (c) what kind of project it is.

#### Step 1 — Locate the project root

Walk **upward** from the given path until you find, in priority order:

1. a `.git/` directory (the real answer 95% of the time)
2. a `.yeet/` directory
3. a `.github/workflows/` directory
4. any ecosystem manifest (`package.json`, `pyproject.toml`, `go.mod`,
   `Cargo.toml`, `pom.xml`, `build.gradle`, `composer.json`, `Gemfile`,
   `*.csproj`, `CMakeLists.txt`, `Makefile`)

Stop at the filesystem root or the user's home directory, whichever comes
first. If nothing matched, treat the given directory as the root and emit an
info diagnostic. For a bare directory the user just created with two files in
it, this still works — that's the point.

`git rev-parse --show-toplevel` is the shortcut, but **don't depend on git
being installed or the project being a repo** — the requirement explicitly
includes locally created projects.

#### Step 2 — Discover workflow files

Search paths, in precedence order:

| Order | Path glob | Notes |
|---|---|---|
| 1 | `.yeet/flows/*.{yml,yaml,json}` | your native location |
| 2 | `.github/workflows/*.{yml,yaml}` | real GitHub Actions — **must work** |
| 3 | `yeet.{yml,yaml,json}` / `.yeet.yml` at root | single-file projects |
| 4 | `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile` | *detect only* — report "found a GitLab CI file, not supported" rather than silently ignoring it. Costs 5 lines, reads as thoughtful. |

Walking rules — get these right or `yeet scan` will hang on someone's monorepo:

```python
EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target", "out",
    ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".gradle", ".next", ".nuxt", "bin", "obj", ".yeet/tmp", ".yeet/runs",
}
MAX_DEPTH      = 5        # from project root
MAX_FILES      = 20_000   # hard stop, then warn "project too large, narrow with --path"
FOLLOW_SYMLINKS = False   # symlink loops will hang you forever
```

Also: track visited inodes (`os.stat().st_ino`) to break hardlink/junction
cycles, and wrap every `os.scandir` in a `PermissionError` handler — on a
company laptop you *will* hit directories you can't read, and crashing there is
an instant bad impression.

Honor `.gitignore` using `pathspec` when the project is a git repo. Add a
`.yeetignore` with identical syntax for non-git projects.

#### Step 3 — Fingerprint the project

Detect the stack so you can pick a base image, auto-generate a workflow, and
warn about mismatches.

| Marker file | Ecosystem | Suggested image | Default build/test |
|---|---|---|---|
| `package.json` | Node | `node:20` | `npm ci` / `npm test` |
| `pnpm-lock.yaml` / `yarn.lock` | Node (variant) | `node:20` | `pnpm i --frozen-lockfile` |
| `pyproject.toml` / `requirements.txt` | Python | `python:3.12` | `pip install -r ...` / `pytest` |
| `go.mod` | Go | `golang:1.22` | `go build ./...` / `go test ./...` |
| `Cargo.toml` | Rust | `rust:1.79` | `cargo build` / `cargo test` |
| `pom.xml` | Java/Maven | `maven:3.9-eclipse-temurin-21` | `mvn -B verify` |
| `build.gradle[.kts]` | Java/Gradle | `gradle:8-jdk21` | `gradle build` |
| `*.csproj` / `*.sln` | .NET | `mcr.microsoft.com/dotnet/sdk:8.0` | `dotnet test` |
| `Gemfile` | Ruby | `ruby:3.3` | `bundle exec rake` |
| `composer.json` | PHP | `php:8.3-cli` | `composer test` |
| `Dockerfile` | Container | *build it* | — |
| `docker-compose.yml` | Multi-service | note it, don't run it | — |
| `CMakeLists.txt` / `Makefile` | C/C++ | `gcc:13` | `make` |

Multiple matches = polyglot project; report all of them and let the workflow
decide. Read `engines.node` from `package.json` and `requires-python` from
`pyproject.toml` to pin the tag rather than guessing.

`yeet scan` output should look like:

```
📦 project: /home/tamizh/demo-api          (git repo, branch: main)
   stack:   Python 3.12 · Docker
   markers: pyproject.toml, Dockerfile, .github/workflows/

🔎 flows found: 2
   ✔ .github/workflows/ci.yml         3 jobs · 11 steps · valid
   ✖ .yeet/flows/deploy.yml           2 errors, 1 warning   → run `yeet check`

💡 ./Dockerfile present → jobs without `cooked_on` will build it
```

#### Step 4 — Bootstrap when nothing is found

If discovery returns zero flows, **don't just error out.** Print the
fingerprint and offer:

```
no flows found in this project.
run `yeet init --auto` to generate one for a Python + Docker project
```

`yeet init --auto` writes a working workflow from the fingerprint table above.
This single feature is what makes the demo sentence "point it at *any* repo"
actually true.

---

### 3.10 Validation Engine — "is this .yml written correctly?"

Your requirement to check standards and reject badly written files. Treat this
as a **first-class product**, not an afterthought — it's the part of the
project a trainer can evaluate without Docker even being installed.

Architecture: five layers, each producing `Diagnostic` objects. Run every layer
that can still run (don't stop at the first error within a layer), but **stop
between layers** — there's no point schema-checking a file that isn't valid
YAML.

```python
@dataclass
class Diagnostic:
    code: str          # "YEET-E203"
    severity: str      # "error" | "warning" | "info"
    message: str       # one line, no jargon
    file: Path
    line: int | None
    col: int | None
    end_col: int | None
    snippet: str | None   # the source line, for the code frame
    help: str | None      # "did you mean `build`?"
    url: str | None       # link to docs/rules.md#yeet-e203
```

#### Layer 0 — File & encoding

| Code | Check |
|---|---|
| `E001` | file unreadable / permission denied |
| `E002` | file is empty or whitespace only |
| `E003` | not valid UTF-8 (report the byte offset) |
| `W004` | UTF-8 BOM present — strip it, warn |
| `E005` | **tab characters used for indentation** — YAML forbids tabs and the native error is unreadable. Catch this yourself with a regex and say so plainly. Extremely common. |
| `W006` | CRLF line endings (works, but warn — ties into §4) |
| `W007` | file >1 MB — probably not a workflow |

#### Layer 1 — YAML syntax

Use `ruamel.yaml` in round-trip mode. On `MarkedYAMLError`, the exception
carries `problem_mark.line` / `.column` — turn that straight into a diagnostic.

| Code | Check |
|---|---|
| `E101` | YAML parse failure (mapping values not allowed, bad indent, unclosed quote…) |
| `E102` | **duplicate keys.** PyYAML silently keeps the last one. Subclass the constructor to raise instead — a duplicated `moves:` key silently dropping half a workflow is a nightmare to debug. |
| `E103` | top-level document is not a mapping (e.g. someone wrote a list) |
| `E104` | multiple YAML documents (`---` separator) in one flow file |
| `W105` | **the `on:` trap.** YAML 1.1 resolves unquoted `on`, `off`, `yes`, `no`, `y`, `n` to booleans. So `on:` parses as the key `True`. GitHub tolerates it; you must too. Normalize `True → "on"` at the key level and warn the user to quote it. Same for a branch literally named `no` becoming `False` ("the Norway problem"). |

**Getting line numbers out of ruamel** (the practical bit most teams miss):

```python
from ruamel.yaml import YAML
yaml = YAML(typ="rt")            # round-trip preserves position data
data = yaml.load(path.read_text(encoding="utf-8"))

# for any CommentedMap:
line, col = data.lc.key("the_grind")     # position of the key
line, col = data.lc.value("the_grind")   # position of its value
# for any CommentedSeq:
line, col = data[2].lc.line, data[2].lc.col
```

Carry `(line, col)` on every IR node from the moment you build it. Retrofitting
positions later is a rewrite — do it on Day 1.

#### Layer 2 — Schema / structure

Normalize aliases (§3.2) **first**, then `jsonschema.validate()` against your
canonical schema.

| Code | Check |
|---|---|
| `E201` | unknown key at this level → `difflib.get_close_matches` against canonical keys *and* your Gen-Z aliases for the "did you mean" |
| `E202` | required key missing (`the_grind`/`jobs`, `moves`/`steps`) |
| `E203` | wrong type (`after: build` where a list is required — though GitHub allows the scalar form, so accept both and normalize) |
| `E204` | step has **both** `bet`/`run` and `yoink`/`uses` |
| `E205` | step has **neither** — an empty step |
| `E206` | empty `the_grind:` / no jobs defined |
| `E207` | invalid job or step id (must match `[A-Za-z_][A-Za-z0-9_-]*`) |
| `E208` | `when:`/`on:` names an event you don't support — list the ones you do |

`jsonschema` errors are notoriously bad by default. Use
`jsonschema.exceptions.best_match(validator.iter_errors(doc))` and convert
`error.absolute_path` (a deque) into a readable path:
`the_grind.build.moves[2].bet`.

#### Layer 3 — Semantic (what schema can't express)

This is where you actually earn marks. All of these are cheap graph/lookup
checks over the IR.

| Code | Check |
|---|---|
| `E301` | `after:`/`needs:` references a job that doesn't exist → suggest nearest name |
| `E302` | dependency **cycle** — print the cycle: `build → test → build` |
| `E303` | duplicate step `id` within a job |
| `E304` | duplicate job key (caught at `E102` but re-check post-normalization) |
| `E305` | `steps.<id>.outputs.*` references a step id that doesn't exist |
| `E306` | `steps.<id>` referenced by a step that runs **before** it |
| `E307` | `needs.<job>.outputs.*` where `<job>` isn't in this job's `needs` |
| `E308` | `matrix.<var>` referenced but not declared in the matrix |
| `E309` | `${{ }}` expression fails to parse (report the offset *inside* the expression) |
| `E310` | unknown context name (`githib.sha`, `env` misspelled) |
| `E311` | unknown function call in an expression |
| `E312` | `matrix.exclude` entry matches no generated leg (usually a typo) |
| `E313` | `yoink:`/`uses:` points at a local path that doesn't exist, or an `action.yml` that's missing/invalid |
| `E314` | required input of an action not supplied in `with:` |
| `E315` | `cooked_on:` value can't be resolved to an image and no `Dockerfile` was found |
| `E316` | `patience:`/`timeout-minutes` not a positive number |
| `E317` | a `secrets.X` is referenced that isn't in the local secret store (**warning** by default, error under `--strict`) |
| `W318` | job is unreachable — nothing needs it and its `when:` can never fire |
| `W319` | `with:` supplies an input the action's `action.yml` doesn't declare |

#### Layer 4 — Standards / lint ("the way it is written")

Warnings, never errors, unless `--strict`. This layer is what turns "it runs"
into "it enforces conventions" — exactly what your brief asked for.

| Code | Rule | Why |
|---|---|---|
| `W401` | workflow or job has no `vibe:`/`name:` | unreadable logs |
| `W402` | action pinned to a moving ref (`@main`, `@master`) instead of a tag or SHA | supply-chain risk |
| `W403` | image tag is `latest` | non-reproducible builds |
| `W404` | **possible hardcoded secret** — regex for `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`, `-----BEGIN .* PRIVATE KEY-----`, plus a Shannon-entropy check (>4.0 bits/char on a 20+ char literal) | the highest-value rule you'll write |
| `W405` | multi-line `bet:`/`run:` without `set -euo pipefail` | silent failures |
| `W406` | `run:` block longer than 50 lines | move it to a script file |
| `W407` | no `patience:`/`timeout-minutes` on a job | a hung job blocks forever |
| `W408` | `delulu: true` / `continue-on-error` on a job that looks like a deploy | dangerous |
| `W409` | absolute host path in a `run:` (`/home/`, `C:\`, `/Users/`) | breaks on every other machine |
| `W410` | file path in `run:` whose case doesn't match on disk | passes on Windows/macOS, fails in the Linux container |
| `W411` | deprecated workflow commands: `::set-output`, `::save-state`, `::set-env` | replaced by the `$GITHUB_OUTPUT` files in §3.6 |
| `W412` | `actions/checkout@v1`/`@v2`, `actions/setup-node@v1` | EOL runtimes |
| `W413` | job with zero steps | dead config |
| `W414` | duplicated step blocks across jobs | suggest a composite action |
| `I415` | style: Gen-Z aliases and canonical keys mixed in one file | consistency nudge |

Make every rule toggleable via `.yeet/lint.yml`:

```yaml
rules:
  W403: error      # promote
  W407: off        # we know, it's a demo
  W415: warning
```

#### The diagnostic report — what the user actually sees

This is the deliverable for "show the message that the .yml file is not written
correctly." Copy the `rustc`/`eslint` presentation; it's the industry standard
and it looks instantly professional.

```
yeet check

✖ .yeet/flows/deploy.yml — this flow ain't it (2 errors, 1 warning)

  error[YEET-E301]  job `deploy` waits on a job that doesn't exist
    ┌─ .yeet/flows/deploy.yml:14:12
    │
 12 │   deploy:
 13 │     cooked_on: ubuntu-latest
 14 │     after: [bild]
    │             ^^^^ no job named `bild` in this flow
    │
    = help: did you mean `build`?
    = docs: docs/rules.md#yeet-e301

  error[YEET-E204]  a step can't have both `bet` and `yoink`
    ┌─ .yeet/flows/deploy.yml:19:9
    │
 18 │       - vibe: publish
 19 │         bet: npm publish
 20 │         yoink: ./.yeet/actions/npm-publish
    │         ^^^^^ pick one: run a command, or use an action
    = docs: docs/rules.md#yeet-e204

  warning[YEET-W404]  possible hardcoded secret
    ┌─ .yeet/flows/deploy.yml:23:20
    │
 23 │         drip: { NPM_TOKEN: npm_9f3aK2xQ... }
    │                            ^^^^^^^^^^^^^^^ looks like a credential
    = help: use `tea.NPM_TOKEN` and `yeet secrets set NPM_TOKEN`

✔ .github/workflows/ci.yml — no notes, this one ate

summary: 1 of 2 flows valid · 2 errors · 1 warning
refusing to run. fix the errors or re-run with --skip-checks (don't).
```

Implementation notes for the code frame renderer (~80 lines, worth it):
- read the source file once, keep lines in memory
- show 2 lines of context above, 1 below
- right-align the gutter line numbers
- clamp `col`/`end_col` to the line length so a bad position never crashes the
  renderer — always `try/except` around frame rendering and fall back to plain
  `file:line: message`
- disable color when `NO_COLOR` is set or stdout isn't a TTY

**Machine-readable output.** `--format json` emits the `Diagnostic` list
directly. `--format sarif` emits SARIF 2.1.0, which VS Code's SARIF Viewer and
GitHub code scanning both consume for free. Showing your own linter's findings
rendered inline in VS Code is a 20-second demo beat that lands very well.

#### Diagnostic code registry

Keep `docs/rules.md` with one section per code: what it means, an example that
triggers it, an example that fixes it, and how to disable it. `yeet explain
YEET-E301` prints that section. Generate the doc's index from the code table so
it can't drift.

Ranges: `E0xx` file · `E1xx` YAML · `E2xx` schema · `E3xx` semantic ·
`W4xx` lint/standards · `I4xx` info.

#### Where validation is wired in

- `yeet check` — layers 0–4, exit 0 / 1 (warnings only, `--strict`) / 2 (errors)
- `yeet run` — layers 0–3 always, hard stop on any error before a container is
  created. Layer 4 runs and prints but doesn't block.
- `yeet watch` — validates on every file change and prints the report; a broken
  file logs and waits rather than crashing the daemon
- `yeet scan` — layer 0–2 only across all discovered flows (fast summary)
- Your `pre-push` git hook — `yeet check --strict`

---

## 4. Cross-platform compatibility checklist

Your hard requirement: WSL+Docker company laptop, plus macOS, Windows, Linux.

**Docker daemon discovery**
```
Linux / WSL / macOS  →  unix:///var/run/docker.sock
Windows native       →  npipe:////./pipe/docker_engine
```
`docker.from_env()` handles both via `DOCKER_HOST`. On failure, print a
platform-specific fix (`Is Docker Desktop running?` / `sudo systemctl start docker`
/ `Enable WSL integration in Docker Desktop → Settings → Resources`).

**WSL path translation.** Detect WSL via `/proc/version` containing
`microsoft`. If the repo lives under `/mnt/c/...`, **warn loudly**: bind-mount
I/O across the Windows filesystem boundary is 10–20× slower and file watching
is unreliable. Recommend moving the repo to `~/`.

**Windows-native paths → container paths.** `C:\Users\x\proj` must be sent to
the Docker API as `/c/Users/x/proj` (or `//c/Users/x/proj` depending on
daemon). Write one `to_container_path()` helper, unit-test it on all three OSes.

**Line endings — the #1 silent killer.** If you write a step script with CRLF,
bash inside the container fails with `$'\r': command not found`. Always:
```python
Path(script).write_bytes(script_text.replace("\r\n", "\n").encode("utf-8"))
```
Also add `.yeet/tmp/** text eol=lf` to `.gitattributes` and tell your team to
set `git config core.autocrlf input`.

**File ownership on Linux.** If the container runs as root, every file it
creates in the mounted workspace becomes root-owned on the host, and the next
`git status` breaks. Pass `user=f"{os.getuid()}:{os.getgid()}"` on Linux/WSL
only — Docker Desktop on macOS/Windows already virtualizes ownership, and
passing a UID there breaks things.

**Case sensitivity.** Linux containers are case-sensitive; macOS and Windows
hosts usually aren't. A workflow referencing `./Src/index.js` will work on a
teammate's Mac and fail in the container. Add a lint warning.

**Shells.** Default `bash` inside containers. For `cooked_on: local`: bash on
Linux/macOS/WSL, `pwsh` (fall back to `powershell`) on Windows. Support an
explicit `shell:` key.

**Terminal colors on Windows.** `rich` enables VT processing automatically, but
add a `--no-color` flag and honor the `NO_COLOR` env var.

**Symlinks on Windows** require Developer Mode. Avoid creating them; copy
instead.

**Long paths on Windows** (>260 chars) — keep your cache dir shallow:
`%LOCALAPPDATA%\yeet\` not a deep nest.

**Config directory per platform:**
```
Linux/WSL:  ~/.config/yeet/  and  ~/.cache/yeet/
macOS:      ~/Library/Application Support/yeet/
Windows:    %APPDATA%\yeet\  and  %LOCALAPPDATA%\yeet\
```
Use `platformdirs` — it's one dependency and removes an entire class of bugs.

---

## 5. Secrets, logging, artifacts

**Secrets.** Sources in precedence order: `--secret K=V` flag → `.yeet/.secrets`
(gitignored, encrypted) → OS keyring → `.env`. Encrypt the file store with
`cryptography.fernet` and a key derived from a passphrase via `scrypt`.
Never write secrets into the workflow file. Add `.yeet/.secrets` and
`.yeet/tmp/` to a generated `.gitignore`.

**Masking.** Maintain a set of secret values. Filter **every** line of stdout
and stderr before it reaches the terminal *or* the log file — replace with
`***`. Also mask base64 and URL-encoded variants of each secret; that's the
gap most homebrew implementations miss and it's a great point to raise in your
presentation.

**Log layout** (use `rich`):
```
● build (node 20)                                      [ cooked ]
  ├─ ✔ pull up the code                                     1.2s
  ├─ ✔ install deps                                        18.4s
  ├─ ✖ run tests                                            4.1s
  │    3 failing, 12 passing — this ain't it chief
  └─ ⊘ deploy                        skipped (not the vibe: build flopped)

flow: ship it fr fr — FLOPPED in 24.9s
```

Persist structured logs to `.yeet/runs/<run-id>/` as JSONL — one object per
log line with `{ts, job, step, stream, text}`. `yeet logs <run-id>` replays it.
Cheap to build, looks professional.

**Artifacts & cache.**
- `loot:` (upload-artifact) → copy to `.yeet/artifacts/<run-id>/<name>/`
- `stash:` (cache) → key = user-supplied string, usually
  `${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}`;
  store a tarball in `~/.cache/yeet/cache/<sha256(key)>.tar.zst`; support
  `restore-keys` prefix matching. `hashFiles()` must glob and hash
  deterministically (sort paths first!).

---

## 6. Team split for four people

Freeze the IR dataclasses and the `aliases.yml` file on Day 0. Then:

| Dev | Owns | Deliverable interface |
|---|---|---|
| **A — Frontend/DSL/Analyzer** | CLI (typer), project root detection + flow discovery + fingerprinting (§3.9), `yeet scan`, YAML loading with positions, alias normalization, JSON Schema, `yeet init --auto` | `analyze(path) -> Project`, `parse(path) -> Workflow` |
| **B — Brains + Validator** | Expression lexer/parser/evaluator, contexts, matrix, DAG + topo sort, `yeet graph`, **and the semantic validation layer (§3.10 L3)** — it's the same graph walk, so one person should own both | `evaluate(expr, ctx)`, `plan(Workflow) -> list[Wave]`, `check_semantic(Workflow) -> list[Diagnostic]` |
| **C — Muscle** | Docker SDK integration, image resolution, Dockerfile build+cache, container lifecycle, volume mounts, path translation, all cross-platform handling | `run_job(Job, ctx) -> JobResult` |
| **D — Glue & polish** | `Diagnostic` dataclass + **code-frame renderer** + `--format json/sarif` + `docs/rules.md` + the lint layer (§3.10 L4), state files (`GITHUB_ENV` etc.), `::` commands, secrets + masking, artifacts/cache, rich logging, watcher + git hooks, packaging, tests, README | `render(list[Diagnostic])`, log sink, `StateStore`, `Trigger` |

**Cross-cutting contract to freeze on Day 0 alongside the IR:** the
`Diagnostic` dataclass. All four of you emit them; only Dev D renders them.
Nobody is allowed to `print()` an error directly.

**Integration rules:**
- `main` is protected; everything through PRs
- Dev D wires an end-to-end smoke test on Day 2 that runs a trivial `echo`
  workflow — it will be broken for two days, that's fine, it's your tripwire
- Daily 15-min sync at a fixed time; anyone blocked >2h escalates

---

## 7. Day-by-day plan (compress if your Friday is sooner)

**Day 0 — Sunday/Monday.** Repo, project skeleton, **IR dataclasses + the
`Diagnostic` dataclass**, `aliases.yml`, `schema.json` skeleton, CI, task board.
Everyone reads `act`'s `pkg/model`.
Ship: `yeet --help` works.

**Day 1.** A: project root detection + flow discovery walker + fingerprint table
(§3.9). B: expression tokenizer + parser. C: Docker connect, pull image, run
`echo hi`, stream logs. D: `Diagnostic` + code-frame renderer + rich logger.
**Ship: `yeet scan` on three different real repos correctly finds their
workflow files.** Cheap, visible, and it unblocks everyone else's test fixtures.

**Day 2.** A: ruamel loading with line/col + alias normalize + schema layer
(L0–L2). B: evaluator + contexts + `if:`. C: container-per-job + `exec` per
step + workspace mount. D: state files + `::group::`/`::error::` parsing.
**Ship (a): `yeet check` catches a broken YAML file with a real code frame.
Ship (b): a single-job, three-step workflow actually runs in Docker.** ← the
two milestones that de-risk the whole week. If (b) slips past Wednesday, cut
matrix and remote `uses:` immediately.

**Day 3.** B: DAG + `needs` + skip semantics **+ semantic layer L3** (same
graph walk — `E301`/`E302`/`E305`–`E308` fall out almost free). C: matrix +
parallel jobs + `Dockerfile` auto-build. A: composite actions loader,
`yeet init --auto`. D: lint layer L4 + secrets + masking.
Ship: multi-job DAG with matrix; `yeet check` catches the top 10 rules.

**Day 4.** C: Docker-type actions, image cache. A: `uses:` remote resolution
(if going for it). B: `hashFiles`, status functions. D: `docs/rules.md`,
`yeet explain`, `--format json`, artifacts + cache + `yeet logs`.
Ship: end-to-end on a real Node repo and a real Python repo neither of you
wrote.

**Day 5.** Triggers: watcher daemon + git hooks. Cross-platform test day —
one person on WSL, one Windows-native, one macOS, one bare Linux. Fix every
path/CRLF/permission bug found. Freeze features here.

**Day 6.** Hardening, README, `yeet graph`, error-message polish, packaging
(`pipx install .` / `pip install .`). Write the demo script. Do **two** dry
runs of the demo end to end.

**Day 7 / Friday.** Demo. Have a recorded video fallback in case Docker
misbehaves on the projector laptop.

---

## 8. Testing

- **Golden files:** `tests/fixtures/<name>.yml` + `<name>.expected.json` for
  parser output. ~20 fixtures covers most regressions.
- **Expression table tests:** a CSV of `expr, context, expected` — dozens of
  cases, one test function.
- **Executor tests:** need Docker; mark `@pytest.mark.docker` and skip when the
  daemon is absent so laptops without Docker still run the unit suite.
- **Cross-platform matrix:** run your test suite in *real* GitHub Actions on
  `ubuntu-latest`, `macos-latest`, `windows-latest`. Using GitHub Actions to
  test your GitHub Actions clone is a genuinely good joke and a genuinely good
  test strategy — lead your presentation with the green matrix badge.
- **Invalid-fixture corpus (do this one properly):** `tests/invalid/<CODE>.yml`
  — one file per diagnostic code, each deliberately broken in exactly one way,
  named after the code it must produce. One parametrized test asserts
  `codes_emitted(f) == {f.stem}`. This gives you ~40 tests for an hour of work,
  proves every rule fires, and catches the classic bug where fixing one rule
  silently breaks another. It's also the single best artifact to show a trainer.
- **Discovery tests:** build fixture project trees under `tmp_path` — a git
  repo, a bare folder, a monorepo with `node_modules`, a symlink loop, a
  directory with no read permission — and assert the analyzer finds the right
  flows and never hangs or crashes.
- **Compatibility corpus:** grab 5–10 real `.github/workflows/*.yml` from
  popular OSS repos (they're just files — `curl` them into `tests/corpus/`),
  run `yeet check` on all of them, and report a "% of syntax supported" number
  plus a list of every unsupported key you hit. Concrete metrics score well,
  and the unsupported-key list writes your §9 non-goals for you.

---

## 9. Scope discipline — say "no" to these, out loud

Explicitly listing non-goals in your README and slides reads as engineering
maturity, not laziness:

- ❌ Windows containers (Linux containers only)
- ❌ Self-hosted runner registration protocol / GitHub API auth
- ❌ Reusable workflows (`uses:` at job level) and `workflow_call`
- ❌ Environments, deployment protection rules, OIDC
- ❌ Service containers (`services:`) — *unless* time permits; it's ~40 lines
  (start containers on a shared network, inject hostnames)
- ❌ Full `@actions/toolkit` API surface
- ❌ Concurrency groups / cancel-in-progress

---

## 10. Things that will bite you (bookmark this list)

1. CRLF in generated step scripts → `$'\r': command not found`
2. Root-owned files after a container run on Linux/WSL
3. `ubuntu:22.04` has no `git`/`node`/`curl` — your workflows mysteriously fail
4. Repo on `/mnt/c/` under WSL → glacial I/O and broken file watching
5. `yaml.load()` instead of `yaml.safe_load()` → arbitrary code execution
6. `eval()` in the expression engine → same, worse
7. Forgetting that each step is a new process — env vars vanish
8. Not debouncing the file watcher → infinite trigger loops (a run writes files
   into the workspace, which triggers a run, which…)
9. Secrets leaking into logs via a subprocess you forgot to filter
10. `hashFiles()` returning different hashes on different OSes because glob
    order differs — **sort the paths**
11. Containers not cleaned up on Ctrl-C → register `atexit` + SIGINT/SIGTERM
    handlers that stop and remove
12. Zombie `docker build` cache growth → add `yeet prune`
13. **`on:` parsing as the boolean `True`** — YAML 1.1 resolves `on`/`off`/
    `yes`/`no` to booleans. Every homebrew runner hits this. Normalize the key.
14. **PyYAML silently swallowing duplicate keys** — two `moves:` keys and half
    your workflow vanishes with no error. Override the constructor to raise.
15. Tab characters for indentation → YAML's native error message is useless.
    Detect it yourself in Layer 0 and say "YAML doesn't allow tabs, use spaces."
16. Building the IR without line/column data, then trying to add diagnostics on
    Day 4. You cannot retrofit this cheaply. Positions on Day 1 or never.
17. Recursing into `node_modules` during discovery → 30-second `yeet scan` on a
    trivial project. Exclude list + depth cap from the start.
18. Symlink loops (or Windows directory junctions) hanging the walker forever →
    `follow_symlinks=False` plus an inode visited-set.
19. `PermissionError` crashing the walk on a corporate laptop → catch per
    directory, emit an info diagnostic, keep going.
20. A validation crash caused by a bad line/column index in the code-frame
    renderer. Your error reporter must never be the thing that errors — clamp
    indices and wrap the renderer in `try/except`.

---

## 11. Demo script for Friday (rehearse this exactly)

Structure it as **analyse → validate → run**, in that order. That's the story
your brief actually describes, and validation demos are far more reliable on a
projector than Docker is.

1. `git clone` a random OSS repo live, then `yeet scan` → it identifies the
   stack and finds `.github/workflows/*.yml` in a project nobody on your team
   wrote. This is the "works on anything" claim, proven in 10 seconds.
2. `yeet check` on that repo → clean. Then on your deliberately broken file →
   the full code-frame report: unknown key with a *did you mean*, a `needs`
   pointing at a nonexistent job, a hardcoded token flagged.
3. `yeet run` on the broken file → **it refuses**, non-zero exit. Show the gate.
4. Fix the file, `yeet init` a fresh project → show the generated Gen-Z workflow
5. Show the **same** workflow in standard GitHub Actions syntax also runs —
   "we're a superset, not a replacement"
6. `yeet graph` → the DAG
7. `yeet run` → live matrix, parallel jobs, grouped colored logs
8. Break a test on purpose → `flopped`, the downstream skip, non-zero exit
9. Show a repo with only a `Dockerfile` → auto-detect, build, cache, run
10. `yeet hooks install` → `git commit` → run fires automatically
11. Show the green GitHub Actions matrix badge (Ubuntu/macOS/Windows) and the
    "% of real-world workflow syntax supported" number from your corpus test
12. One slide: architecture diagram, the diagnostic code registry, non-goals,
    what you'd build next

Total: 8–10 minutes. Time it. Steps 1–3 are your strongest material and need no
Docker — if the projector laptop's Docker misbehaves, you still have a demo.