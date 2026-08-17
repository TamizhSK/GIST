"""D21 — the secret store is encrypted, and stays that way.

The bug these lock down: this module's docstring claimed "Encrypted local
store" while it wrote `json.dumps(secrets)` in plaintext to a file inside the
project directory — the same directory that gets bind-mounted into every
container.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yeet.secrets import store
from yeet.secrets.store import SecretsError, SecretsLocked

PASSPHRASE = "correct horse battery staple"
TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"


@pytest.fixture(autouse=True)
def _no_ambient_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's own keyring/env must not decide these tests."""
    monkeypatch.delenv(store.PASSPHRASE_ENV, raising=False)
    monkeypatch.setattr(store, "_keyring_get", lambda: None)


def test_round_trip(tmp_path: Path) -> None:
    """D21's acceptance: `yeet secrets set NPM_TOKEN` round-trips."""
    store.save_secret(tmp_path, "NPM_TOKEN", TOKEN, passphrase=PASSPHRASE)
    loaded = store.load_secrets(tmp_path, passphrase=PASSPHRASE)
    assert loaded["NPM_TOKEN"] == TOKEN


def test_the_value_is_not_on_disk_in_the_clear(tmp_path: Path) -> None:
    """The whole point. Grep the raw bytes for the secret."""
    store.save_secret(tmp_path, "NPM_TOKEN", TOKEN, passphrase=PASSPHRASE)
    raw = (tmp_path / store.SECRETS_FILE).read_bytes()

    assert TOKEN.encode() not in raw
    assert b"NPM_TOKEN" not in raw, "the key names leak the shape of the store"

    envelope = json.loads(raw.decode("utf-8"))
    assert envelope["kdf"] == "scrypt"
    assert "ciphertext" in envelope


def test_a_wrong_passphrase_is_rejected(tmp_path: Path) -> None:
    store.save_secret(tmp_path, "NPM_TOKEN", TOKEN, passphrase=PASSPHRASE)
    with pytest.raises(SecretsError, match="wrong passphrase"):
        store.load_secrets(tmp_path, passphrase="hunter2")


def test_each_write_uses_a_fresh_salt(tmp_path: Path) -> None:
    """Same secret, same passphrase, different ciphertext."""
    store.save_secret(tmp_path, "A", "value", passphrase=PASSPHRASE)
    first = (tmp_path / store.SECRETS_FILE).read_text(encoding="utf-8")
    store.save_secret(tmp_path, "B", "value", passphrase=PASSPHRASE)
    second = (tmp_path / store.SECRETS_FILE).read_text(encoding="utf-8")

    assert json.loads(first)["salt"] != json.loads(second)["salt"]


def test_a_locked_store_raises_rather_than_returning_nothing(tmp_path: Path) -> None:
    """Silence here would mean a run whose secrets are simply not masked."""
    store.save_secret(tmp_path, "NPM_TOKEN", TOKEN, passphrase=PASSPHRASE)
    with pytest.raises(SecretsLocked):
        store.load_secrets(tmp_path)


def test_no_store_is_not_an_error(tmp_path: Path) -> None:
    assert store.load_secrets(tmp_path) == {}
    assert store.list_secrets(tmp_path) == []


# --- precedence ---------------------------------------------------------------


def test_precedence_flag_beats_store_beats_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=from-env\nB=from-env\nC=from-env\n", encoding="utf-8")
    store.save_secret(tmp_path, "A", "from-store", passphrase=PASSPHRASE)
    store.save_secret(tmp_path, "B", "from-store", passphrase=PASSPHRASE)

    loaded = store.load_secrets(tmp_path, {"A": "from-flag"}, passphrase=PASSPHRASE)

    assert loaded["A"] == "from-flag"
    assert loaded["B"] == "from-store"
    assert loaded["C"] == "from-env"


def test_dotenv_quirks(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "\n"
        'QUOTED="value"\n'
        "SINGLE='value'\n"
        "export EXPORTED=value\n"
        "WITH_EQUALS=a=b\n"
        "not a pair\n",
        encoding="utf-8",
    )
    loaded = store.load_secrets(tmp_path)
    assert loaded == {
        "QUOTED": "value",
        "SINGLE": "value",
        "EXPORTED": "value",
        "WITH_EQUALS": "a=b",
    }


# --- passphrase resolution ----------------------------------------------------


def test_env_var_supplies_the_passphrase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store.save_secret(tmp_path, "NPM_TOKEN", TOKEN, passphrase=PASSPHRASE)
    monkeypatch.setenv(store.PASSPHRASE_ENV, PASSPHRASE)
    assert store.load_secrets(tmp_path)["NPM_TOKEN"] == TOKEN


def test_keyring_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """`keyring` is not a declared dependency (plan.md §8), so its absence must
    be an ordinary None rather than an ImportError at module load."""
    import builtins

    real_import = builtins.__import__

    def no_keyring(name: str, *args: object, **kwargs: object) -> object:
        if name == "keyring":
            raise ImportError("no keyring here")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "_keyring_get", store._keyring_get)
    monkeypatch.setattr(builtins, "__import__", no_keyring)

    assert store._keyring_get() is None
    assert store.keyring_set("anything") is False


# --- list / remove ------------------------------------------------------------


def test_list_returns_names_only(tmp_path: Path) -> None:
    store.save_secret(tmp_path, "B_TOKEN", "b", passphrase=PASSPHRASE)
    store.save_secret(tmp_path, "A_TOKEN", "a", passphrase=PASSPHRASE)

    names = store.list_secrets(tmp_path, passphrase=PASSPHRASE)
    assert names == ["A_TOKEN", "B_TOKEN"]
    assert "a" not in names and "b" not in names


def test_remove(tmp_path: Path) -> None:
    store.save_secret(tmp_path, "GONE", "x", passphrase=PASSPHRASE)
    assert store.remove_secret(tmp_path, "GONE", passphrase=PASSPHRASE) is True
    assert store.list_secrets(tmp_path, passphrase=PASSPHRASE) == []
    assert store.remove_secret(tmp_path, "GONE", passphrase=PASSPHRASE) is False


# --- migration ----------------------------------------------------------------


def _write_legacy(root: Path) -> Path:
    path = root / store.SECRETS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"OLD_TOKEN": "legacy"}), encoding="utf-8")
    return path


def test_a_legacy_plaintext_store_is_still_readable(tmp_path: Path) -> None:
    """Losing someone's tokens silently is worse than reading an old format."""
    _write_legacy(tmp_path)
    assert store.is_legacy_plaintext(tmp_path) is True
    assert store.load_secrets(tmp_path)["OLD_TOKEN"] == "legacy"


def test_writing_migrates_the_whole_store_to_encrypted(tmp_path: Path) -> None:
    _write_legacy(tmp_path)
    store.save_secret(tmp_path, "NEW_TOKEN", "new", passphrase=PASSPHRASE)

    assert store.is_legacy_plaintext(tmp_path) is False
    raw = (tmp_path / store.SECRETS_FILE).read_bytes()
    assert b"legacy" not in raw

    loaded = store.load_secrets(tmp_path, passphrase=PASSPHRASE)
    assert loaded == {"OLD_TOKEN": "legacy", "NEW_TOKEN": "new"}


def test_a_corrupt_store_says_so(tmp_path: Path) -> None:
    path = tmp_path / store.SECRETS_FILE
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SecretsError):
        store.load_secrets(tmp_path)
