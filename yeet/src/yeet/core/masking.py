"""Secret masking — the pure string half of `secrets/`.

This lives in core, not in `secrets/`, for one concrete reason: the executor
has to mask every line it emits, and `executor` and `secrets` are independent
siblings at tier 5. `lint-imports` rejects that edge. So the *policy* (where
secrets come from, how they're decrypted) stays in `secrets/store.py`, and the
*mechanism* lives here where anyone may import it.

Masking a value also masks its base64 and URL-encoded forms. That is the gap
most homebrew runners leave open: a token is safe in the log right up until
some tool prints it inside a URL or a basic-auth header.

Owner: Dev D
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from urllib.parse import quote

MASK = "***"

MIN_LENGTH = 4
"""Values shorter than this are not masked. Masking `"1"` would redact every
line that contains a digit, which is worse than not masking at all."""


class Masker:
    """A set of secret values, and a filter that redacts them from a line.

    Not thread-safe for concurrent `add()`; the executor adds from the stream
    reader of a single job and reads from the same thread.
    """

    __slots__ = ("_values", "_ordered")

    def __init__(self, values: Iterable[str] = ()) -> None:
        self._values: set[str] = set()
        self._ordered: tuple[str, ...] = ()
        for value in values:
            self.add(value)

    def add(self, value: str) -> None:
        """Register a secret and every encoding of it we know how to produce."""
        added = False
        for variant in self._variants(value):
            if len(variant) >= MIN_LENGTH and variant not in self._values:
                self._values.add(variant)
                added = True
        if added:
            # Longest first, so a secret that contains another secret as a
            # substring is redacted whole rather than leaving a tail behind.
            self._ordered = tuple(sorted(self._values, key=len, reverse=True))

    def update(self, values: Iterable[str]) -> None:
        for value in values:
            self.add(value)

    def mask(self, line: str) -> str:
        """Redact every known secret. Must never raise — it sits in the log path."""
        for value in self._ordered:
            if value in line:
                line = line.replace(value, MASK)
        return line

    @staticmethod
    def _variants(value: str) -> list[str]:
        raw = value.strip()
        if not raw:
            return []
        encoded = raw.encode("utf-8", errors="replace")
        b64 = base64.b64encode(encoded).decode("ascii")
        url_b64 = base64.urlsafe_b64encode(encoded).decode("ascii")
        return [
            raw,
            b64,
            b64.rstrip("="),  # padding is routinely stripped in headers
            url_b64.rstrip("="),
            quote(raw, safe=""),
        ]

    def __len__(self) -> int:
        return len(self._values)

    def __bool__(self) -> bool:
        return bool(self._values)
