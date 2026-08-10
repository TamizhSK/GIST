"""Protocol both backends implement. Keeps Docker out of everyone else's imports.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""
from __future__ import annotations

class Backend(Protocol):
    def run_job(self, job: "Job", ctx: object) -> "JobResult": ...
