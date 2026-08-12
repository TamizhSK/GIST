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
| **Start here** | [`yeet/docs/handbook.md`](yeet/docs/handbook.md) — architecture, commands, working style |
| **New to the codebase** | [`yeet/docs/understanding-yeet.md`](yeet/docs/understanding-yeet.md) — how it works, in diagrams |
| **The code** | [`yeet/`](yeet/) |
| **The design, and why** | [`yeet/docs/architecture.md`](yeet/docs/architecture.md) |
| **Machine setup** | [`yeet/docs/getting-started.md`](yeet/docs/getting-started.md) |
| **Every diagnostic code** | [`yeet/docs/rules.md`](yeet/docs/rules.md) (generated) |
| **Who builds what, day by day** | [`plan.md`](plan.md) |
| **Decisions we had to make** | [`yeet/docs/adr/`](yeet/docs/adr/) |

## Status

Implemented end to end and green. `scan → check → graph → run → logs` works on
both the dialect and canonical GitHub Actions syntax. See
[`yeet/docs/handbook.md`](yeet/docs/handbook.md) §7 for what is and is not done.

```bash
cd yeet
python -m venv .venv && source .venv/bin/activate   # PS: .venv\Scripts\Activate.ps1
pip install -e ".[dev]" && pre-commit install
make check                                          # every gate CI runs
yeet --help
```

Note the layout: the Python project lives in `yeet/`, while CI lives in
`.github/workflows/` **here at the repo root** — GitHub only discovers workflows
at the root, so it cannot live next to the code it tests.
