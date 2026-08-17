# ADR 0001 — We record architecture decisions

## Status
Accepted

## Context
Four people are building one system in a week. Decisions made in a hallway
conversation get re-litigated on Thursday when someone hits a wall.

## Decision
Every choice that affects more than one subsystem gets a numbered file in
`docs/adr/`. One page: Context, Decision, Consequences. No approval process —
write it, link it in the PR.

## Consequences
Costs ten minutes each. Gives us the "why" section of the final presentation
for free, and stops the same argument happening twice.

---

## ADRs to write in week one
- 0002 — Why Python and not Go
- 0003 — Why one parser plus an alias table, not two parsers
- 0004 — Why one container per job with exec-per-step
- 0005 — Why validation is a five-layer pipeline that gates execution
- 0006 — Why ruamel.yaml over PyYAML (position data)
