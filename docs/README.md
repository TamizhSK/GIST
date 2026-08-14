# yeet — documentation

The docs are split by audience so you only ever read what you need. Pick a lane:

| You are… | Start with |
|---|---|
| Just want to run it | the root [`README.md`](../README.md) — install, quick start, secrets |
| New to the codebase | [`understanding-yeet.md`](understanding-yeet.md) — what the thing is, with diagrams |
| Joining the team / contributing | [`handbook.md`](handbook.md) — how we work, how a command travels through the code |
| Need to set up a machine | [`getting-started.md`](getting-started.md) — Day-0 setup and the dev loop |
| Want to know *why* it's built this way | [`architecture.md`](architecture.md) + [`adr/`](adr/) — the design rationale |
| A diagnostic code fired | [`rules.md`](rules.md) — every code, **generated** from `core/codes.py` |
| Tracking what's been done | [`../plan.md`](../plan.md) (the build plan) + [`history/`](history/) (session logs) |

**Two rules that make the rest easy:**

1. **`docs/rules.md` is generated.** Never hand-edit it — edit `core/codes.py`
   and run `make rules`.
2. **`docs/architecture.md` is the design doc; `plan.md` is the assignment.**
   Every source file carries `Owner:` and `Tier:` in its docstring and says
   "See docs/architecture.md" — that pointer is the source of truth for *where
   a piece of code fits*.

## The shortest path to being productive

```
1.  make check              # all six gates, exactly what CI runs — must be green
2.  yeet --help             # the ten commands
3.  yeet scan → check → graph → run → logs   # the whole product, five commands
4.  docs/handbook.md §4     # how a command travels through the code
5.  docs/handbook.md §6     # the call-site rule — the lesson that cost us most
```

## The history folder

[`history/`](history/) holds the session-by-session record of how the project
was built: `session-context.md` (what each session shipped) and `undone.md`
(an independent review of that work, plus the defects found). Read them as a
timeline — newest work is at the bottom. They are a maintainer's log, not a
tutorial.

---

_If a section below is a wall of text, the docs have regressed. Each file has a
single job; add a new file rather than growing one._
