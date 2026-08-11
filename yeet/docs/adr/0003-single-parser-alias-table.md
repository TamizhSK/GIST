# ADR 0003 — Why one parser plus an alias table, not two parsers

## Status
Accepted

## Context
Workflow syntax varies slightly between GitHub Actions and alternative dialects (`manual` vs `workflow_dispatch`).

## Decision
We use a single parser with an append-only alias table (`parser/aliases.yml`) that normalizes key/event variants into canonical IR early.

## Consequences
- Eliminates duplicate parsing logic and AST maintenance across subsystems.
- Keeps intermediate representation (`IR`) strictly canonical.
