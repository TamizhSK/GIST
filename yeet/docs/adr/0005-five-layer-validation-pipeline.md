# ADR 0005 — Why validation is a five-layer pipeline that gates execution

## Status
Accepted

## Context
Running containers for malformed or invalid YAML workflows wastes CPU, time, and pollutes local execution state.

## Decision
Validation is structured into 5 explicit layers (Layer 0 File -> Layer 1 YAML -> Layer 2 Schema -> Layer 3 Semantic -> Layer 4 Lint). Execution is hard-stopped before any container is spawned if Layers 0–3 produce any error.

## Consequences
- Immediate, clear feedback on workflow syntax and DAG cycle errors.
- Prevents dirty state or container creation on invalid workflows.
