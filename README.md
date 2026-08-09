# Building Your Own Local GitHub Actions Runner

**Working codename used throughout:** `yeet` (rename freely — the CLI name is a one-line constant)

---

## 0. Read this first: the one decision that makes or breaks the week

You have ~1 week and 4 people. The single highest-leverage thing you can do is
**define the internal representation (IR) on Day 0 and freeze it.** Everything
else — parser, scheduler, Docker executor, logger — talks only to the IR, never
to each other. That's what lets four people write code in parallel without
blocking.

```
 .yml / .json          IR (plain dicts / dataclasses)          side effects
┌──────────────┐      ┌──────────────────────────┐      ┌──────────────────┐
│  Parser +    │ ───▶ │ Workflow → Jobs → Steps  │ ───▶ │ Executor         │
│  Alias layer │      │ + Contexts + Triggers    │      │ (Docker / local) │
└──────────────┘      └──────────────────────────┘      └──────────────────┘
       ▲                          │                              │
       │                          ▼                              ▼
  schema.json              DAG Scheduler                    Log stream
```

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
PyYAML        # parsing (use yaml.safe_load ONLY)
jsonschema    # workflow schema validation w/ good error messages
docker        # Docker Engine API SDK
rich          # colored grouped log output, live status tree
watchdog      # filesystem triggers
lark          # expression grammar (or hand-roll a Pratt parser)
keyring       # OS-native secret store (optional, nice touch)
pytest        # golden-file tests
```

---

## 3. System architecture — the eight subsystems

### 3.1 CLI (entrypoint)

```
yeet init                    # scaffold .yeet/flows/main.yml in current repo
yeet run [flow] [--job X]    # run once
yeet run --event push        # simulate a trigger
yeet validate                # schema-check without running
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
| **A — Frontend/DSL** | CLI (typer), YAML/JSON loading, alias normalization, JSON Schema, error messages with line numbers, `yeet init` templates | `parse(path) -> Workflow` |
| **B — Brains** | Expression lexer/parser/evaluator, contexts, matrix expansion, DAG build + topo sort, `if:` semantics, `yeet graph` | `evaluate(expr, ctx) -> Any`, `plan(Workflow) -> list[Wave]` |
| **C — Muscle** | Docker SDK integration, image resolution, Dockerfile build+cache, container lifecycle, volume mounts, path translation, all cross-platform handling | `run_job(Job, ctx) -> JobResult` |
| **D — Glue & polish** | State files (`GITHUB_ENV` etc.), `::` workflow commands, secrets + masking, artifacts/cache, rich logging, watcher + git hooks, packaging, tests, README | log sink, `StateStore`, `Trigger` |

**Integration rules:**
- `main` is protected; everything through PRs
- Dev D wires an end-to-end smoke test on Day 2 that runs a trivial `echo`
  workflow — it will be broken for two days, that's fine, it's your tripwire
- Daily 15-min sync at a fixed time; anyone blocked >2h escalates

---

## 7. Day-by-day plan (compress if your Friday is sooner)

**Day 0 — Sunday/Monday.** Repo, project skeleton, IR dataclasses, `aliases.yml`,
`schema.json` skeleton, CI, task board. Everyone reads `act`'s `pkg/model`.
Ship: `yeet --help` works.

**Day 1.** A: parser + normalize + validate. B: expression tokenizer + parser.
C: Docker connect, pull image, run `echo hi`, stream logs. D: rich logger,
run-id, log persistence.
Ship: `yeet validate` gives real errors.

**Day 2.** A: `yeet init` templates. B: evaluator + contexts + `if:`.
C: container-per-job + `exec` per step + workspace mount.
D: state files + `::group::`/`::error::` parsing.
**Ship: a single-job, three-step workflow actually runs in Docker.** ← the
milestone that de-risks the whole week.

**Day 3.** B: DAG + `needs` + skip semantics. C: matrix + parallel jobs +
`Dockerfile` auto-build. A: composite actions loader. D: secrets + masking.
Ship: multi-job DAG with matrix.

**Day 4.** C: Docker-type actions, image cache. A: `uses:` remote resolution
(if going for it). B: `hashFiles`, status functions. D: artifacts + cache +
`yeet logs`.
Ship: end-to-end on a real Node and a real Python repo.

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
- **Compatibility corpus:** grab 5 real `.github/workflows/*.yml` from popular
  OSS repos, run `yeet validate` on them, and report a "% of syntax supported"
  number. Concrete metrics score well.

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

---

## 11. Demo script for Friday (rehearse this exactly)

1. `yeet init` in a fresh repo → show the generated Gen-Z workflow
2. Show the **same** workflow written in standard GitHub Actions syntax also
   runs — "we're a superset, not a replacement"
3. `yeet graph` → the DAG
4. `yeet run` → live matrix, parallel jobs, grouped colored logs
5. Break a test on purpose → show `flopped`, the downstream skip, and the
   non-zero exit code
6. Show a repo with only a `Dockerfile` → auto-detect, build, cache, run
7. `yeet hooks install` → `git commit` → run fires automatically
8. Show the green GitHub Actions matrix badge proving it works on
   Ubuntu/macOS/Windows
9. Show `yeet validate` against a real workflow file from a popular OSS repo
10. One slide: architecture diagram, non-goals, what you'd build next

Total: 8 minutes. Time it.