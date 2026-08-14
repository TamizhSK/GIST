# ADR 0004 — Why one container per job with exec-per-step

## Status
Accepted

## Context
Running each step in a separate container loses local state (`$GITHUB_ENV`, working directory changes, disk cache).

## Decision
Create one persistent Docker container per job, and run each step via `exec_run` inside that container.

## Consequences
- Fast step execution without container cold-starts.
- Natural state propagation across steps via `$GITHUB_ENV` / `$GITHUB_OUTPUT`.
