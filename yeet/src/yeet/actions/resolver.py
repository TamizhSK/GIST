"""uses: -> local path | remote clone | docker. Cache under ~/.yeet/actions.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
NOTE: resolves `uses:` into IR only. The EXECUTOR runs it — see plan.md 3.3.
See docs/architecture.md
"""

from __future__ import annotations
