"""ONE container per job, exec per step. Never docker-run per step.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""
from __future__ import annotations

KEEPALIVE_CMD = ["tail", "-f", "/dev/null"]


class DockerBackend:
    def run_job(self, job, ctx):
        raise NotImplementedError
