"""Encrypted local store. Precedence: flag > .yeet/.secrets > keyring > .env.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md

This module used to say "Encrypted local store" in this docstring and write
`json.dumps(secrets)` to disk in plaintext, with the declared `cryptography`
dependency unused. `.yeet/.secrets` is inside the project directory, which is
the directory that gets bind-mounted into every container and the one people
tar up and mail around — so it is now Fernet (AES-128-CBC + HMAC), with the key
derived from a passphrase by scrypt.

**Where the passphrase comes from**, in order, all non-interactive:

1. the `passphrase=` argument (the CLI prompts and passes it),
2. `$YEET_PASSPHRASE`,
3. the OS keyring, *if* `keyring` is installed.

`keyring` is deliberately an optional import rather than a dependency: adding
one is a plan.md §8 "announce in chat first" item, and this works without it.
`pip install keyring` upgrades the experience with no code change.

**Nothing here prompts, prints or raises to the user.** Tier 5 has no terminal.
A locked store raises `SecretsLocked` and the CLI decides what that means.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SECRETS_FILE = ".yeet/.secrets"
KEYRING_SERVICE = "yeet"
KEYRING_USERNAME = "store-passphrase"
PASSPHRASE_ENV = "YEET_PASSPHRASE"

FORMAT_VERSION = 1
#: ~100 ms on a laptop. High enough to matter, low enough that `yeet run`
#: paying it once per invocation is not felt.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class SecretsError(RuntimeError):
    """Something is wrong with the secret store itself."""


class SecretsLocked(SecretsError):
    """The store is encrypted and we have no passphrase for it."""


# --- passphrase ---------------------------------------------------------------


def resolve_passphrase(explicit: str | None = None) -> str | None:
    """The passphrase, or None. Never prompts — see the module docstring."""
    if explicit:
        return explicit
    from_env = os.environ.get(PASSPHRASE_ENV)
    if from_env:
        return from_env
    return _keyring_get()


def _keyring_get() -> str | None:
    try:
        import keyring  # noqa: PLC0415 - optional dependency, imported on use
    except ImportError:
        return None
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:  # noqa: BLE001 - a locked/absent backend must not be fatal
        return None
    return str(value) if value else None


def keyring_set(passphrase: str) -> bool:
    """Remember the passphrase in the OS keyring. False if unavailable."""
    try:
        import keyring  # noqa: PLC0415
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, passphrase)
    except Exception:  # noqa: BLE001
        return False
    return True


# --- crypto -------------------------------------------------------------------


def _derive(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _encrypt(secrets: dict[str, str], passphrase: str) -> str:
    salt = os.urandom(16)
    token = Fernet(_derive(passphrase, salt)).encrypt(
        json.dumps(secrets, sort_keys=True).encode("utf-8")
    )
    envelope = {
        "version": FORMAT_VERSION,
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": token.decode("ascii"),
    }
    return json.dumps(envelope, indent=2)


def _decrypt(envelope: dict[str, Any], passphrase: str) -> dict[str, str]:
    try:
        salt = base64.b64decode(envelope["salt"])
        kdf = Scrypt(
            salt=salt,
            length=32,
            n=int(envelope.get("n", SCRYPT_N)),
            r=int(envelope.get("r", SCRYPT_R)),
            p=int(envelope.get("p", SCRYPT_P)),
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        raw = Fernet(key).decrypt(envelope["ciphertext"].encode("ascii"))
    except InvalidToken as exc:
        raise SecretsError("wrong passphrase for .yeet/.secrets") from exc
    except (KeyError, ValueError, TypeError) as exc:
        raise SecretsError(f"{SECRETS_FILE} is corrupt: {exc}") from exc

    data = json.loads(raw.decode("utf-8"))
    return {str(k): str(v) for k, v in data.items()}


# --- file layer ---------------------------------------------------------------


def _path(root: Path) -> Path:
    return root / SECRETS_FILE


def _read_envelope(root: Path) -> dict[str, Any] | None:
    path = _path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SecretsError(f"{SECRETS_FILE} could not be read: {exc}") from exc
    if not isinstance(data, dict):
        raise SecretsError(f"{SECRETS_FILE} is not a secret store")
    return data


def is_legacy_plaintext(root: Path) -> bool:
    """True for a store written by the pre-encryption version.

    Kept readable on purpose — silently losing someone's tokens is a worse
    outcome than a loud warning — but `save_secret` always rewrites the whole
    file encrypted, so setting any one secret migrates the store.
    """
    try:
        envelope = _read_envelope(root)
    except SecretsError:
        return False
    return envelope is not None and "ciphertext" not in envelope


def _write(root: Path, secrets: dict[str, str], passphrase: str) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_encrypt(secrets, passphrase), encoding="utf-8")
    # Best effort: no-op on Windows, and not the security boundary — the
    # encryption is. It stops a careless `cat *` in a shared checkout.
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def _read(root: Path, passphrase: str | None) -> dict[str, str]:
    envelope = _read_envelope(root)
    if envelope is None:
        return {}
    if "ciphertext" not in envelope:  # legacy plaintext
        return {str(k): str(v) for k, v in envelope.items()}
    resolved = resolve_passphrase(passphrase)
    if not resolved:
        raise SecretsLocked(
            f"{SECRETS_FILE} is encrypted. Set ${PASSPHRASE_ENV}, or run "
            f"`yeet secrets list` to be prompted."
        )
    return _decrypt(envelope, resolved)


# --- public API ---------------------------------------------------------------


def load_secrets(
    root: Path,
    overrides: dict[str, str] | None = None,
    *,
    passphrase: str | None = None,
) -> dict[str, str]:
    """Everything we can find, in precedence order (later wins).

    Raises `SecretsLocked` when an encrypted store exists and no passphrase is
    available. `cmd_run` catches that, says so, and runs with `--secret` and
    `.env` only — a missing passphrase must not stop a build that does not
    need any secrets, but it must never be silent either.
    """
    secrets: dict[str, str] = {}
    secrets.update(read_dotenv(root))
    secrets.update(_read(root, passphrase))
    if overrides:
        secrets.update(overrides)
    return secrets


def read_dotenv(root: Path) -> dict[str, str]:
    """`.env`, lowest precedence. Never fails: it is not our file."""
    env_file = root / ".env"
    out: dict[str, str] = {}
    if not env_file.exists():
        return out
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.startswith("export "):
            key = key[len("export ") :]
        out[key.strip()] = value.strip().strip("'\"")
    return out


def save_secret(root: Path, key: str, value: str, *, passphrase: str | None = None) -> None:
    """Set one secret, rewriting the store encrypted."""
    resolved = resolve_passphrase(passphrase)
    if not resolved:
        raise SecretsLocked(
            f"a passphrase is required to write {SECRETS_FILE} "
            f"(set ${PASSPHRASE_ENV} or let `yeet secrets set` prompt you)"
        )
    secrets = _read(root, resolved)
    secrets[key] = value
    _write(root, secrets, resolved)


def list_secrets(root: Path, *, passphrase: str | None = None) -> list[str]:
    """Names only. Never returns, logs or prints a value."""
    return sorted(_read(root, passphrase))


def remove_secret(root: Path, key: str, *, passphrase: str | None = None) -> bool:
    """Remove one secret. True if it was there."""
    resolved = resolve_passphrase(passphrase)
    secrets = _read(root, resolved)
    if key not in secrets:
        return False
    if not resolved:
        raise SecretsLocked(f"a passphrase is required to rewrite {SECRETS_FILE}")
    del secrets[key]
    _write(root, secrets, resolved)
    return True
