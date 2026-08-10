"""Encrypted local store (Fernet + scrypt). Precedence: flag > file > keyring > .env.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""
from __future__ import annotations
