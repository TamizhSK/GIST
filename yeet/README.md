# yeet

A local, GitHub Actions-compatible workflow runner — with a dialect of its own.

Point it at any project (cloned from GitHub or created locally). It finds the
workflow files, tells you whether they're written correctly, and runs them in
Docker on your machine.

```bash
yeet scan .        # what is this project, and what flows does it have?
yeet check .       # is the .yml written correctly?  (5 validation layers)
yeet run           # run it in Docker
```

## Start here

**[`docs/handbook.md`](docs/handbook.md)** — the twenty-minute orientation:
architecture, every command, and how we work. Read that first.

Then, as needed: [`docs/architecture.md`](docs/architecture.md) for the design
rationale (amended by [`docs/adr/0007`](docs/adr/0007-tier-rule-consequences.md)),
[`../plan.md`](../plan.md) for the file-by-file ownership map,
[`docs/getting-started.md`](docs/getting-started.md) for machine setup, and
[`docs/rules.md`](docs/rules.md) for every diagnostic code (generated from
`core/codes.py` by `make rules` — never hand-edited).

## Status

All five subsystems are implemented and wired end to end. `yeet scan → check →
graph → run → logs` works on both the dialect and canonical GitHub Actions
syntax; `cooked_on: local` runs without Docker at all.

```
make check     five gates green (lint · format · imports · types · noprint · test)
pytest         671 fast tests, plus 18 behind `@pytest.mark.docker`
mypy src       101 source files, strict
lint-imports   2 contracts kept, 0 broken
```

Remaining gaps are listed in `docs/handbook.md` §7.

## Development

```bash
python -m venv .venv
# Linux/macOS/WSL:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
pre-commit install
git config core.autocrlf input   # skip this and \r bites you on Thursday

make test      # fast loop, run constantly
make check     # everything CI runs — before every push
make fix       # repairs what check complains about
```

## Non-goals

See `docs/architecture.md` §9. We say no on purpose.
