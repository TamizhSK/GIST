# yeet

A local, GitHub Actions-compatible workflow runner — with a dialect of its own.

Point it at any project (cloned from GitHub or created locally). It finds the
workflow files, tells you whether they're written correctly, and runs them in
Docker on your machine.

```bash
yeet scan .            # what is this project, and what flows does it have?
yeet check .           # is the .yml written correctly?  (5 validation layers)
yeet secrets import    # collect the secrets/vars its workflows need into .env
yeet run               # run it
```

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

With [pipx](https://pipx.pypa.io) already on the machine, or straight from pip:

```bash
pipx install git+https://github.com/TamizhSK/GIST
pip install git+https://github.com/TamizhSK/GIST     # into the venv you're in
```

Needs **Python 3.10+** (Ubuntu 22.04 LTS and its WSL image ship 3.10). Docker is optional — jobs with `cooked_on: local`
(`runs-on: local`) run in your own shell, so you can validate and run workflows
before you install a daemon. To remove it: `yeet-uninstall`, or
`rm -rf ~/.local/share/yeet ~/.local/bin/yeet`.

## Secrets and variables

A workflow you just cloned reads `${{ secrets.NPM_TOKEN }}` and
`${{ vars.AWS_REGION }}`, and nothing except the workflow files says so.
`yeet secrets import` reads them out, writes every name it finds to `.env`,
and fills in the ones your shell already exports:

```console
$ yeet secrets import
  + AWS_REGION  (variable)
  = NPM_TOKEN   (secret)  ← from your environment
```

`yeet run` then resolves both. The distinction matters at run time: values
read as `secrets.*` are redacted from the log and from `.yeet/runs/`, values
read as `vars.*` are not — masking `vars.NODE_ENV=production` would turn every
"production" in your build output into `***`.

Existing entries are never overwritten, so it is safe to re-run when someone
adds a workflow. `.env` holds plaintext and is gitignored; `yeet secrets set
<NAME>` keeps a value in the passphrase-encrypted store instead.

## Start here

**[`docs/handbook.md`](docs/handbook.md)** — the twenty-minute orientation:
architecture, every command, and how we work. Read that first.

Then, as needed: [`docs/architecture.md`](docs/architecture.md) for the design
rationale (amended by [`docs/adr/0007`](docs/adr/0007-tier-rule-consequences.md)),
[`plan.md`](plan.md) for the file-by-file ownership map,
[`docs/getting-started.md`](docs/getting-started.md) for machine setup, and
[`docs/rules.md`](docs/rules.md) for every diagnostic code (generated from
`core/codes.py` by `make rules` — never hand-edited).

## Status

All five subsystems are implemented and wired end to end. `yeet scan → check →
graph → run → logs` works on both the dialect and canonical GitHub Actions
syntax; `cooked_on: local` runs without Docker at all.

```
make check     six gates green (lint · format · imports · types · noprint · test)
pytest         787 fast tests, plus 18 behind `@pytest.mark.docker`
mypy src       102 source files, strict
lint-imports   2 contracts kept, 0 broken
```

Remaining gaps are listed in `docs/handbook.md` §7.

## Development

```bash
git clone https://github.com/TamizhSK/GIST && cd GIST

python -m venv .venv
source .venv/bin/activate         # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
pre-commit install
git config core.autocrlf input    # skip this and \r bites you on Thursday

make test      # fast loop, run constantly
make check     # everything CI runs — before every push
make fix       # repairs what check complains about
```

The package is at the repo root: `src/yeet/`, `tests/`, `pyproject.toml`. It
used to live one directory down in `yeet/`, which meant `pip install
git+<url>` — the way most people install a tool from a repo — failed with
"neither setup.py nor pyproject.toml found". CI no longer needs a
`working-directory`, either.

## Non-goals

See `docs/architecture.md` §9. We say no on purpose.
