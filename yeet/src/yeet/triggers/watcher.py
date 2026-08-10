"""watchdog daemon. DEBOUNCE or a run's own writes retrigger it forever.

Owner: Dev D
Tier: 6 — may import from: everything below tier 6
See docs/architecture.md
"""

from __future__ import annotations

DEBOUNCE_MS = 500
