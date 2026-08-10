"""Exceptions for *bugs*, not for user errors. User errors are Diagnostics.

Owner: Dev D
Tier: 0 — may import from: nothing (core is a leaf)
See docs/architecture.md
"""
from __future__ import annotations

class YeetInternalError(Exception):
    """Something we did wrong. Never shown raw to the user."""
