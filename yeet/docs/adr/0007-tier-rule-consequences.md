# ADR 0007 — Independent siblings, and the three indirections they force

## Status
Accepted (Day 0)

## Context

`pyproject.toml` enforces the tier rule with an `import-linter` layers contract.
Siblings on one layer are separated by `|`, which in import-linter means
**independent**: they may not import each other.

We verified this rather than assuming it. Adding
`from yeet.secrets import masking` to `yeet/executor/script.py` and running
`lint-imports` produces:

```
Layered architecture (a module may only import from lower tiers) BROKEN
yeet.executor is not allowed to import yeet.secrets:
- yeet.executor.script -> yeet.secrets.masking (l.12)
```

Three flows in the design need exactly that forbidden edge:

1. the executor must mask secrets in every line it emits (`secrets/`)
2. the executor must persist JSONL run logs (`storage/`)
3. the executor must run resolved actions (`actions/`)

and a fourth, one tier down:

4. Layer 3 validation must detect `needs:` cycles, which the guide says to share
   with the scheduler in `planner/graph.py` — but `validation` is tier 3 and
   `planner` is tier 4, so that import is *upward*, which is the thing the
   contract exists to prevent.

## Decision

We keep the contract as written and invert the dependencies instead. Relaxing
the contract (import-linter also accepts `:` between siblings, meaning "may
import each other") was rejected: the sibling rule is what keeps the executor
free of policy, and every workaround below is independently worth having.

1. **`core/masking.py`** — the pure `Masker` (add a value, redact a line, plus
   its base64 and URL-encoded variants). `secrets/store.py` keeps only the
   policy: where secrets come from and how they are decrypted. The executor
   redacts values without ever learning them.

2. **`core/events.py`** — `LogEvent` plus a `LogSink` Protocol. The executor
   calls `sink.emit()`. `storage.runs.RunStore` writes JSONL,
   `reporting.console.RunConsole` draws the live tree, `FanOut` does both, and
   `ListSink` is the in-memory test double. The CLI decides which.

3. **`actions/` moves to tier 2**, beside `parser/`. It is a pure resolver:
   `uses:` in, IR out. It executes nothing. The executor (tier 5) consumes it.

4. **`core/graph.py`** — `find_cycle()` and `topo_waves()` over a plain
   `{node: [deps]}` map. `planner/graph.py` is a thin Job-shaped adapter;
   Layer 3 calls the same function for E302. The algorithm is written once, as
   the guide intended, just at the bottom of the stack rather than the middle.

## Consequences

- Four new files in `core/`, all tier 0, all dependency-free.
- The executor is testable with no filesystem, no Docker and no secret store —
  pass it a `ListSink` and an empty `Masker`.
- `secrets/masking.py` is deleted; `core/masking.py` replaces it.
- Anyone adding a tier-5 module should expect to write an indirection like
  these rather than a direct import. That is the cost, and it is the point.
- `lint-imports` runs in CI and in `make check`, so a regression is caught at
  push time rather than during a Thursday merge.
