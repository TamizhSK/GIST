"""DATA ONLY: marker file -> ecosystem -> suggested image + default commands.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""
from __future__ import annotations

MARKERS = {
    "package.json": ("node", "node:20", ["npm ci", "npm test"]),
    "pyproject.toml": ("python", "python:3.12", ["pip install -e .", "pytest"]),
    "go.mod": ("go", "golang:1.22", ["go build ./...", "go test ./..."]),
    # ... fill from architecture.md 3.9 step 3
}
