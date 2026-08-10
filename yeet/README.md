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

## Status

Day 0 skeleton. See `docs/architecture.md` for the design and
`docs/rules.md` for the diagnostic code registry.

## Development

```bash
python -m venv .venv
# Linux/macOS/WSL:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
pre-commit install

pytest -m "not docker"     # unit tests, no Docker needed
lint-imports               # enforces the tier rule
yeet --help
```

## Non-goals

See `docs/architecture.md` §9. We say no on purpose.
