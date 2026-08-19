# Writing flows, and running them

The user-facing manual: how to write a workflow in yeet's dialect, where to put
the file, and every command that runs it locally.

Nothing here is required. **A canonical `.github/workflows/ci.yml` runs
unchanged** — the dialect is a superset, applied as a key-rewrite the moment
the YAML is loaded, so the two spellings are equally legal in the same file, in
the same repo, in the same mapping (just not for the same key twice — see
[collisions](#a-key-may-only-be-spelled-once)).

- [The dialect, in one table](#the-dialect-in-one-table)
- [A complete flow](#a-complete-flow)
- [Where yeet looks for flows](#where-yeet-looks-for-flows)
- [Running it](#running-it)
- [Steps that work on every machine](#steps-that-work-on-every-machine)
- [When it goes wrong](#when-it-goes-wrong)

---

## The dialect, in one table

LEFT is what you may write; RIGHT is the canonical GitHub Actions key it means.
The table lives in [`src/yeet/parser/aliases.yml`](../src/yeet/parser/aliases.yml)
and adding to it costs one line and no code.

| Write this | …and it means | Where |
|---|---|---|
| `vibe:` | `name:` | workflow, job, step |
| `when:` | `on:` | workflow |
| `the_grind:` / `missions:` | `jobs:` | workflow |
| `cooked_on:` | `runs-on:` | job |
| `after:` / `waits_for:` | `needs:` | job |
| `moves:` | `steps:` | job |
| `bet:` / `cook:` | `run:` | step |
| `yoink:` / `borrow:` | `uses:` | step |
| `only_if:` / `no_cap_if:` | `if:` | job, step |
| `drip:` | `env:` | workflow, job, step |
| `tea:` | `secrets:` | job (reusable workflows) |
| `squad:` | `strategy:` | job |
| `multiverse:` | `matrix:` | inside `squad:` |
| `patience:` | `timeout-minutes:` | job, step |
| `delulu:` / `its_fine:` | `continue-on-error:` | job, step |
| `where:` | `working-directory:` | step |

One value, rather than a key:

| Write this | …and it means |
|---|---|
| `manual:` under `when:` | `workflow_dispatch:` — the hand-triggered event |

And the words a run reports itself with:

| Status | Printed as |
|---|---|
| success | `slayed` |
| failure | `flopped` |
| partial | `mid` |
| running | `cooked` |
| skipped | `skipped (not the vibe)` |

### Where the rewrite does NOT apply

Aliases are rewritten only where a key is a **schema** key. Everywhere a key is
your own data, it is left exactly as you wrote it:

```yaml
the_grind:
  after:                 # a JOB called `after`. Still called `after`.
    cooked_on: local
    moves:
      - yoink: ./.github/actions/greet
        with:
          when: friday   # an action INPUT called `when`. Not `on`.
      - bet: echo "$where"
        drip:
          where: here    # an ENV VAR called `where`. Not working-directory.
```

Job IDs, `env:` names, `with:` inputs, `matrix:` variables, `secrets:` names,
`outputs:` names and the contents of `on:` are all yours. A blind rewrite of
those turned real workflows into different workflows, which is the one failure
a local runner may never have.

### A key may only be spelled once

`name:` and `vibe:` in the same mapping is an error (`YEET-E106`), not a
precedence puzzle:

```yaml
vibe: build            # error: two spellings of `name` in one mapping
name: build it
```

There is no honest winner to pick, and quietly dropping one would run a
workflow you did not write.

---

## A complete flow

Everything below is valid, checked by `yeet check`, and uses the dialect for
every key that has one:

```yaml
vibe: ship it

when:
  push:
    branches: [main]
  manual:                     # workflow_dispatch — `yeet run --event workflow_dispatch`

drip:                         # workflow-level env, inherited by every job
  NODE_ENV: test

the_grind:

  warmup:
    cooked_on: local          # your own shell — no Docker needed
    moves:
      - vibe: say hello
        bet: echo "running on your own machine"

  build:
    cooked_on: ubuntu-latest  # a container
    after: [warmup]           # needs:
    squad:
      multiverse:
        flavor: [vanilla, chocolate]
    moves:
      - yoink: actions/checkout@v4

      - vibe: build ${{ matrix.flavor }}
        id: baked
        bet: |
          set -euo pipefail
          echo "baking ${{ matrix.flavor }}"
          echo "cake=${{ matrix.flavor }}" >> "$GITHUB_OUTPUT"

      - vibe: read the output back
        bet: echo "the cake was ${{ steps.baked.outputs.cake }}"

      - vibe: only on a push
        only_if: ${{ github.event_name == 'push' }}
        bet: echo "this ran because the event was a push"
        patience: 5           # timeout-minutes
        delulu: false         # continue-on-error

      - vibe: in a subdirectory, with its own env
        where: docs           # working-directory
        drip:
          GREETING: hi
        bet: echo "$GREETING from $(pwd)"
```

`${{ }}` expressions are GitHub's, unchanged: `github`, `env`, `job`, `steps`,
`runner`, `matrix`, `needs`, `secrets`, `inputs` and `vars`, with the same
functions (`success()`, `failure()`, `always()`, `contains()`, `fromJSON()`, …).

`cooked_on: local` is the one runner label that is ours. It runs the job in
your own shell instead of a container, which is what makes a machine with no
Docker still able to go end to end.

---

## Where yeet looks for flows

`yeet` walks **down** from the project root and takes every YAML file that sits
under a directory it recognises — at any depth, with any nesting beneath it. In
precedence order:

| Rank | Layout | Extensions |
|---|---|---|
| 1 | `.yeet/flows/**` (and `.yeet/**`) | `.yml` `.yaml` `.json` |
| 2 | `.github/workflows/**`, `.gitea/workflows/**`, `.forgejo/workflows/**` | `.yml` `.yaml` |
| 3 | `workflows/**`, `flows/**` — anywhere, with no `.github` above them | `.yml` `.yaml` |
| 4 | a root `yeet.yml`, `yeet.yaml`, `yeet.json`, `.yeet.yml` | — |

So all of these are found, and `yeet scan` names which rule found each one:

```
.yeet/flows/main.yml
.github/workflows/ci.yaml
.github/workflows/reusable/build.yml
workflows/deploy.yml                    ← no .github anywhere
packages/api/.github/workflows/ci.yml   ← a monorepo, six levels deep
yeet.yml
```

Precedence **orders** the list; it does not truncate it. `yeet check` and
`yeet graph` take every flow they find; `yeet run` with no flow name takes the
first — highest rank, then shallowest, so a repo's own workflow wins over a
vendored example three directories down.

`.gitignore` and `.yeetignore` are honoured, `node_modules`/`.venv`/`dist` and
friends are skipped, and a `.gitlab-ci.yml`, `azure-pipelines.yml` or
`Jenkinsfile` is reported as unsupported rather than silently ignored.

```console
$ yeet scan
project: ~/code/app
   git:     main
   stack:   Python 3.12 · Docker
   markers: pyproject.toml

flows found: 2
   [OK] .yeet/flows/main.yml [yeet]        valid
   [OK] workflows/deploy.yml [workflows]   valid
```

---

## Running it

### Start one

```console
$ yeet init            # writes .yeet/flows/main.yml
$ yeet init --auto     # …generated from what the project actually is
```

### The five you will use

```console
$ yeet scan            # what is this project, and what flows does it have?
$ yeet check           # is it written correctly?      no Docker needed
$ yeet graph           # the job DAG: matrix legs expanded, waves in order
$ yeet run             # run it
$ yeet logs            # replay the last run
```

Every command is a **prefix of `yeet run`**: `scan` stops after analysis,
`check` after validation, `graph` after planning. And any of them takes a path
— a project directory or a single flow file:

```console
$ yeet check workflows/deploy.yml
$ yeet graph ~/code/app
```

### `yeet run`

```console
$ yeet run                          # every job of the first flow found
$ yeet run deploy                   # the flow named deploy.yml (name or stem)
$ yeet run --job build              # one job
$ yeet run --event workflow_dispatch  # pretend it was hand-triggered
$ yeet run --jobs 1                 # serially, instead of one thread per wave
$ yeet run --secret TOKEN=abc123    # highest-precedence secret, masked in the log
$ yeet run --path ~/code/app        # somewhere else
$ yeet run -v                       # every line, no folding
$ yeet run --tui                    # full-screen dashboard instead of streaming
$ yeet run --clean                  # empty workspace; `checkout` fills it, as on GitHub
$ yeet run --offline                # never fetch an action; use the cache only
```

By default your working directory is mounted, so **uncommitted edits are what
run** — the point of a local runner. `--clean` is the honest rehearsal: it
catches the workflow with no `checkout` step and the one that only passes
because of a file you have not committed.

### The rest

```console
$ yeet watch                # re-check on every save; leave it in a second terminal
$ yeet doctor               # is this machine set up to run a workflow?
$ yeet explain YEET-E301    # what a diagnostic code means
$ yeet secrets import       # collect the secrets/vars the flows need into .env
$ yeet secrets set NPM_TOKEN   # store one in the local encrypted store
$ yeet secrets list         # names only, never values
$ yeet hooks install        # run flows from post-commit / pre-push
$ yeet prune                # this project's images, containers and .yeet/tmp
$ yeet prune --actions      # also empty the `uses:` cache
$ yeet logs 20260818-221940-9aa3   # a specific run
$ yeet upgrade --check      # is there a newer yeet?  changes nothing
$ yeet upgrade              # get it
```

### Staying current

```console
$ yeet upgrade --check          # ask; installs nothing
$ yeet upgrade                  # install the latest published release
$ yeet upgrade --version v0.9   # pin, or go back
```

It downloads the wheel attached to the latest release and installs it into the
environment yeet already lives in — no git, no re-clone, no rebuild. On a
development checkout it refuses and points at `git pull`, because upgrading
would replace your working tree with a published wheel.

**On 0.8 or earlier this command is not there.** It shipped in 0.9, and a
command cannot be back-fitted into a version already on a laptop. Re-run the
install one-liner for your platform once and you are current, with `yeet
upgrade` available from then on. The installer names both versions so you can
see it happened:

```
      !   replacing yeet 0.8
      ok  yeet 0.10
      ok  upgraded 0.8 -> 0.10
```

The whole picture — every install method, rolling back, and pinning in CI — is
in [`upgrading.md`](upgrading.md).

### Exit codes

| Code | Meaning |
|---|---|
| 0 | everything passed |
| 1 | a job failed |
| 2 | the workflow file is wrong — **no container was ever created** |
| 3 | Docker is needed and not available |

---

## Steps that work on every machine

A `cooked_on: local` job runs in **your** shell, and that is not the same shell
everywhere. With no explicit `shell:`, a step gets:

| Where | Shell |
|---|---|
| in a container (any `cooked_on:` image) | `bash` |
| `cooked_on: local` on Linux/macOS | `bash` |
| `cooked_on: local` on Windows | `pwsh`, or `powershell` if PowerShell 7 is absent |

That is GitHub's rule too, and it means a bash-only step in a `local` job is a
step that only runs on some machines. Two ways to be explicit:

```yaml
      - vibe: works everywhere, because it says which shell it wants
        shell: bash
        bet: echo "cake=vanilla" >> "$GITHUB_OUTPUT"

      - vibe: the PowerShell spelling of the same thing
        shell: pwsh
        bet: 'Add-Content -Path $env:GITHUB_OUTPUT -Value "cake=vanilla"'
```

`$GITHUB_OUTPUT`, `$GITHUB_ENV`, `$GITHUB_PATH` and `$GITHUB_STEP_SUMMARY`
work in either shell — yeet reads those files back whatever encoding your
shell wrote them in (Windows PowerShell writes UTF-16). `$YEET_OUTPUT` and
friends name the same files, if you prefer the dialect all the way down.

Jobs with an image (`cooked_on: ubuntu-latest`) need Docker; `local` jobs never
do. `yeet doctor` says which of the two this machine can do.

---

## When it goes wrong

`yeet check` runs five layers and prints rustc-style frames. Layers 0–3 are the
**gate**: any error there and the run stops before a container exists. Layer 4
is lint — it prints opinions and never blocks.

```console
$ yeet check
error[YEET-E301]: job `deploy` needs `bulid`, but no job by that name exists
 --> .yeet/flows/main.yml:10:5
   |
 8 |   deploy:
 9 |     cooked_on: local
10 |     after: [bulid]
   |     ^
11 |     moves:
   |
   = note: known jobs: build, deploy
[FAIL] .yeet/flows/main.yml: 1 error(s), 0 warning(s)
```

Every code is documented — `yeet explain YEET-E301`, or
[`rules.md`](rules.md) for the whole list.

Useful shapes:

```console
$ yeet check --strict            # warnings block too
$ yeet check --format json       # for an editor or a script
$ yeet check --format sarif      # for a code-scanning viewer
```

---

**See also:** [`README.md`](../README.md) for install and the tour ·
[`rules.md`](rules.md) for every diagnostic · [`handbook.md`](handbook.md) if
you are working on yeet itself rather than with it.
