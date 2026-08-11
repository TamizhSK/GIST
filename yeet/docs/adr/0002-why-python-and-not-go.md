# ADR 0002 — Why Python and not Go

## Status
Accepted

## Context
Runner projects like `act` are written in Go. We had to decide whether to build `yeet` in Go or Python.

## Decision
We chose Python 3.11+ using standard library, `typer`, `ruamel.yaml`, `rich`, and `docker-py`.

## Consequences
- Expressive data structures (`dataclasses(slots=True)`) and rapid prototyping.
- Rich ecosystem for AST manipulation, regex parsing, and CLI presentation.
- Easy cross-platform deployment via pip / virtualenv.
