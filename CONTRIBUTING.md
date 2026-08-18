# Contributing

Thanks for looking. This is a small project with a strong opinion about where
code goes, and most of that opinion is enforced by a command rather than by
review.

## Setup

```bash
git clone https://github.com/TamizhSK/GIST && cd GIST
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]" && pre-commit install
make check                                          # must be green before you start
```

`make image` builds the base container every `runs-on: ubuntu-latest` job uses.
You only need it for `make docker`.

## The one command

```bash
make check
```

`lint · format · imports · types · noprint · test`, in that order, and it is
byte-for-byte what CI runs. A green `make check` is a green PR; that is the
whole reason it is short. `make fix` repairs the two mechanical ones.

Docker tests are separate and need a daemon:

```bash
make docker
```

## The tier rule

`src/yeet/` is layered, and **imports only ever point downhill**. `executor`
never imports `cli`; `parser` never imports `executor`. Siblings marked
independent in `pyproject.toml` may not import each other either.

This is not a convention to police in review — `lint-imports` fails the build.
If two modules at the same tier need to share something, it moves down into
`core/`. See [`docs/architecture.md`](docs/architecture.md) and
[`docs/adr/0007`](docs/adr/0007-tier-rule-consequences.md).

## Rules and diagnostics

Every diagnostic code lives in `src/yeet/core/codes.py`, and
[`docs/rules.md`](docs/rules.md) is **generated** from it:

```bash
make rules      # regenerate; never hand-edit rules.md
```

CI regenerates and diffs, so a new code without `make rules` is a red build.
`rules.md` also ships inside the wheel — it is what `yeet explain` prints.

## Tests

Prefer adding a case to `tests/invalid/` or `tests/corpus/` over writing a new
bespoke test. Both are table-driven and cost close to nothing per case:

- `tests/invalid/<CODE>.yml` — a file that must produce exactly that code.
- `tests/corpus/` — real workflows from real repositories that must parse.

Where a check needs a test that does not exist, **write the test** rather than
verifying by hand. A manual check passes once.

Two things tests here are expected to do that are not universal:

- **Name the bug.** A docstring that says what broke and why is worth more than
  one that restates the assertion.
- **Force the environment.** Most of this tool's failures are about a machine
  we are not on — a cp1252 console, a stripped `$HOME`, an interpreter without
  `tarfile`'s `filter=`. Monkeypatch the condition rather than skipping.

## Commit messages

Conventional-commit prefix, plus the dev role when the change belongs to one
owner's area:

```
fix(parser): DEV-A aliases only rewrite at schema key positions
feat(cli): DEV-C yeet doctor
docs: record session-13 in docs/history/undone.md
```

## Comments

Short lines. Explain **why**, not what — the code says what. If a comment is
longer than the code it explains, it probably belongs in `docs/` or in the
module docstring.

## Pull requests

- One concern per PR.
- `make check` green, and say so.
- If it changes behaviour on a platform you cannot test, say which one.
- Paste real terminal output for anything user-facing.
