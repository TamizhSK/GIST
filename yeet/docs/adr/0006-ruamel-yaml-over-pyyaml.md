# ADR 0006 — Why ruamel.yaml over PyYAML (position data)

## Status
Accepted

## Context
Error diagnostic reporting requires exact line and column line numbers for code-frame visualization.

## Decision
Use `ruamel.yaml` in round-trip mode (`typ="rt"`), which preserves `.lc.value(key)` source line and column numbers on dict keys.

## Consequences
- Enables high-precision code-frame reporting (`rustc`/`eslint` style).
- Allows detection of duplicate keys and comment preservation.
