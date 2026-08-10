# yeet

A local, GitHub Actions-compatible workflow runner — with a dialect of its own.

Point it at any project, cloned from GitHub or created locally. It finds the
workflow files, tells you whether they're written correctly, and runs them in
Docker on your machine.

```bash
yeet scan .        # what is this project, and what flows does it have?
yeet check .       # is the .yml written correctly?  (5 validation layers)
yeet run           # run it in Docker
```

Real `.github/workflows/*.yml` files run unchanged — the dialect is a key-rewrite
pass over one canonical parser, not a second parser. We're a superset, not a
replacement.

## Where things are

| | |
|---|---|
| **The code** | [`yeet/`](yeet/) — start with [`yeet/README.md`](yeet/README.md) |
| **The design, and why** | [`yeet/docs/architecture.md`](yeet/docs/architecture.md) |
| **Day 0 → your first green run** | [`yeet/docs/getting-started.md`](yeet/docs/getting-started.md) |
| **Who builds what, day by day** | [`plan.md`](plan.md) |
| **Decisions we had to make** | [`yeet/docs/adr/`](yeet/docs/adr/) |

## Status

Day 0 skeleton, wired and green. Every subsystem is a stub with a frozen
signature — see `plan.md` §5 for the file-by-file ownership map.

```bash
cd yeet
python -m venv .venv && source .venv/bin/activate   # PS: .venv\Scripts\Activate.ps1
pip install -e ".[dev]" && pre-commit install
make check                                          # ruff · format · imports · mypy · pytest
yeet --help
```
