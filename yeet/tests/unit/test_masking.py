"""Unit tests for core secret masking (Dev D / Task D2)."""

from __future__ import annotations

import base64
from urllib.parse import quote

from yeet.core.masking import MASK, Masker


def test_masker_empty() -> None:
    masker = Masker()
    assert len(masker) == 0
    assert not masker
    assert masker.mask("hello world") == "hello world"


def test_masker_raw_secret() -> None:
    masker = Masker(["supersecret123"])
    assert len(masker) > 0
    assert bool(masker)
    assert masker.mask("authorization: supersecret123 token") == f"authorization: {MASK} token"


def test_masker_base64_variants() -> None:
    secret = "ghp_abcdef1234567890"
    masker = Masker([secret])

    # Plain text
    assert masker.mask(f"token = {secret}") == f"token = {MASK}"

    # Base64 encoded
    b64_secret = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    assert masker.mask(f"Basic {b64_secret}") == f"Basic {MASK}"

    # Stripped padding variant
    b64_stripped = b64_secret.rstrip("=")
    assert masker.mask(f"Header {b64_stripped}") == f"Header {MASK}"


def test_masker_url_encoding() -> None:
    secret = "pass#word?123"
    masker = Masker([secret])

    url_encoded = quote(secret, safe="")
    assert masker.mask(f"http://user:{url_encoded}@host.com") == f"http://user:{MASK}@host.com"


def test_masker_min_length_floor() -> None:
    # Values shorter than 4 chars should be ignored to avoid redacting normal digits/chars
    masker = Masker(["1", "ab", "xyz"])
    assert len(masker) == 0
    assert masker.mask("Count: 1, 2, 3") == "Count: 1, 2, 3"


test_short_and_long = ("secret", "secret_long_value")


def test_longest_first_replacement() -> None:
    masker = Masker(["secret", "secret_long_value"])
    # If short was replaced first, "secret_long_value" would become "***_long_value"
    # Replacing longest first produces "***" for the whole string.
    assert masker.mask("value is secret_long_value") == f"value is {MASK}"


def test_masker_update() -> None:
    masker = Masker()
    masker.update(["secret_one_123", "secret_two_456"])
    assert masker.mask("secret_one_123 and secret_two_456") == f"{MASK} and {MASK}"
