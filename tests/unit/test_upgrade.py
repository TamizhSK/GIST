"""`yeet upgrade` — the path from the version someone installed to the one that shipped.

No network in here. The GitHub call is the one thing that must be faked, and
everything worth testing is on either side of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from yeet.cli import cmd_upgrade as up


@pytest.fixture(autouse=True)
def _no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery is cached per process and would otherwise hit the real keychain."""
    from yeet.core import gitcreds

    gitcreds.reset_cache()
    monkeypatch.setattr(gitcreds, "discover_token", lambda *a, **k: gitcreds.Credential())


# --- comparing versions --------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("0.9", "0.8", True),
        ("0.8", "0.8", False),
        ("0.7", "0.8", False),
        ("0.8.1", "0.8", True),
        ("0.8", "0.8.1", False),
        # The one a string comparison gets wrong, and the reason this is not one.
        ("0.10", "0.9", True),
        ("1.0", "0.99", True),
    ],
)
def test_version_ordering(candidate: str, current: str, expected: bool) -> None:
    assert up.is_newer(candidate, current) is expected


def test_a_non_numeric_piece_does_not_raise() -> None:
    """A `v0.9rc1` tag must not turn `yeet upgrade` into a traceback."""
    assert up.is_newer("0.9rc1", "0.8") is True


# --- reading a release ---------------------------------------------------------


def _release_json(tag: str = "v0.9", assets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "assets": assets
        if assets is not None
        else [
            {"name": "yeet-0.9.tar.gz", "browser_download_url": "https://x/sdist"},
            {"name": "yeet-0.9-py3-none-any.whl", "browser_download_url": "https://x/wheel"},
        ],
    }


def test_the_wheel_is_what_it_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not the sdist: the wheel needs no build, no compiler and no git."""
    monkeypatch.setattr(up, "_get_json", lambda _url: _release_json())
    assert up._release() == ("0.9", "https://x/wheel")


def test_the_v_prefix_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tags are `v0.9`; `__version__` is `0.9`. Comparing them raw never matches."""
    monkeypatch.setattr(up, "_get_json", lambda _url: _release_json("v0.9"))
    assert up._release()[0] == "0.9"


def test_a_release_with_no_wheel_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(up, "_get_json", lambda _url: _release_json(assets=[]))
    with pytest.raises(up.UpgradeError, match="no wheel"):
        up._release()


def test_a_pinned_tag_asks_for_that_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def capture(url: str) -> dict[str, Any]:
        seen.append(url)
        return _release_json("v0.7")

    monkeypatch.setattr(up, "_get_json", capture)
    assert up._release("v0.7")[0] == "0.7"
    assert seen == [up.API_TAG.format(tag="v0.7")]


def test_no_tag_asks_for_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(up, "_get_json", lambda url: (seen.append(url), _release_json())[1])
    up._release()
    assert seen == [up.API_LATEST]


# --- talking to GitHub ---------------------------------------------------------


class _Response:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self.ok = 200 <= status < 300
        self.reason = "Testing"
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def test_rate_limiting_is_explained_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    """60/hour per IP is shared by an office; the fix is a token, not waiting."""
    monkeypatch.setattr(up.requests, "get", lambda *a, **k: _Response(403))
    with pytest.raises(up.UpgradeError, match="rate-limited"):
        up._get_json("https://example/x")


def test_a_missing_release_points_at_the_releases_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(up.requests, "get", lambda *a, **k: _Response(404))
    with pytest.raises(up.UpgradeError, match="no such release"):
        up._get_json("https://example/x")


def test_a_network_failure_is_a_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise up.requests.RequestException("name resolution failed")

    monkeypatch.setattr(up.requests, "get", boom)
    with pytest.raises(up.UpgradeError, match="could not reach GitHub"):
        up._get_json("https://example/x")


def test_a_token_is_sent_when_there_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifts the API limit from 60/hour to 5000, and costs nothing to pass."""
    from yeet.core import gitcreds

    monkeypatch.setattr(gitcreds, "discover_token", lambda *a, **k: gitcreds.Credential("t", "env"))
    assert up._headers()["Authorization"] == "Bearer t"


def test_no_token_means_no_authorization_header(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "Authorization" not in up._headers()


# --- refusing to clobber a working tree ----------------------------------------


def test_a_dev_checkout_is_detected() -> None:
    """This test file lives in one, so the answer is knowable without a fixture."""
    found = up.dev_checkout()
    assert found is not None
    assert (found / "pyproject.toml").is_file()


def test_an_installed_copy_is_not_a_dev_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """site-packages has no pyproject.toml and no .git above it."""
    fake = tmp_path / "site-packages" / "yeet" / "cli" / "cmd_upgrade.py"
    fake.parent.mkdir(parents=True)
    fake.touch()
    monkeypatch.setattr(up, "__file__", str(fake))
    assert up.dev_checkout() is None
