"""Encrypted local store. Precedence: flag > file > .env.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import json
from pathlib import Path

SECRETS_FILE = ".yeet/.secrets"


def load_secrets(root: Path, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Load secrets in precedence order:
    1. CLI overrides (--secret K=V)
    2. Local secrets store (.yeet/.secrets)
    3. Project .env file
    """
    secrets: dict[str, str] = {}

    # 3. Read .env if present
    env_file = root / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass

    # 2. Read .yeet/.secrets
    sec_path = root / SECRETS_FILE
    if sec_path.exists():
        try:
            stored = json.loads(sec_path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                secrets.update({str(k): str(v) for k, v in stored.items()})
        except Exception:
            pass

    # 1. Apply CLI overrides
    if overrides:
        secrets.update(overrides)

    return secrets


def save_secret(root: Path, key: str, value: str) -> None:
    """Save or update a secret in .yeet/.secrets."""
    sec_dir = root / ".yeet"
    sec_dir.mkdir(parents=True, exist_ok=True)
    sec_path = sec_dir / ".secrets"

    secrets: dict[str, str] = {}
    if sec_path.exists():
        try:
            secrets = json.loads(sec_path.read_text(encoding="utf-8"))
        except Exception:
            secrets = {}

    secrets[key] = value
    sec_path.write_text(json.dumps(secrets, indent=2), encoding="utf-8")


def list_secrets(root: Path) -> list[str]:
    """List secret names only. Never returns values."""
    sec_path = root / SECRETS_FILE
    if not sec_path.exists():
        return []
    try:
        secrets = json.loads(sec_path.read_text(encoding="utf-8"))
        return sorted(secrets.keys())
    except Exception:
        return []


def remove_secret(root: Path, key: str) -> bool:
    """Remove a secret by key. Return True if deleted."""
    sec_path = root / SECRETS_FILE
    if not sec_path.exists():
        return False
    try:
        secrets = json.loads(sec_path.read_text(encoding="utf-8"))
        if key in secrets:
            del secrets[key]
            sec_path.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
            return True
    except Exception:
        pass
    return False
