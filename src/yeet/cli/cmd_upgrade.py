"""yeet upgrade — get the version that shipped after the one you installed.

Owner: Dev C
Tier: 7 — may import from: anything
See docs/architecture.md

WHY THIS FILE EXISTS. The installers replace an existing install correctly and
have since v0.7 — but the only way to get an update was to remember the
`curl … | sh` one-liner and to know that there was something to get. Neither
is reasonable to expect. A tool people install once and then run for months has
to be able to say "there is a newer one" and to fetch it, or it silently
becomes the old version on every machine that ever installed it.

**IT INSTALLS THE RELEASE WHEEL, NOT A GIT REF.** `pip install git+https://…`
needs git, needs a full clone, and builds from source; the release already
carries `yeet-<v>-py3-none-any.whl` (release.yml attaches it, and gates on the
tag matching `__version__`). Downloading one file is faster, works on a machine
with no git, and installs exactly the artifact CI tested.

**IT REFUSES ON A DEV CHECKOUT.** An editable install points at a working tree;
`pip install --upgrade` over it would replace the user's own source with a
published wheel and silently discard whatever they were working on. `git pull`
is what they want and this says so.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import requests
import typer

from yeet import __version__
from yeet.core import gitcreds
from yeet.reporting.theme import SYMBOL_WARN

REPO = "TamizhSK/YEET"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
API_TAG = f"https://api.github.com/repos/{REPO}/releases/tags/{{tag}}"
RELEASES_URL = f"https://github.com/{REPO}/releases"

TIMEOUT_S = 20
"""One HTTP call against the GitHub API. Short: `yeet upgrade --check` may run
from a shell prompt, and a hung network must not be indistinguishable from a
slow one."""


class UpgradeError(RuntimeError):
    """Something went wrong that the user can read and act on."""


# --- asking GitHub what exists ------------------------------------------------


def _headers() -> dict[str, str]:
    """Ask as the user when we can, anonymously when we cannot.

    Unauthenticated GitHub API calls are limited to 60 per hour PER IP, which a
    shared office address or a CI runner burns through without anyone doing
    anything wrong. `gitcreds` already found a token for the container work; the
    same one lifts this to 5000/hour and costs nothing to pass.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"yeet/{__version__}",
    }
    found = gitcreds.discover_token()
    if found:
        headers["Authorization"] = f"Bearer {found.token}"
    return headers


def _get_json(url: str) -> dict[str, Any]:
    """GET, through `requests` rather than `urllib`.

    NOT a style preference. `urllib` validates TLS against the platform trust
    store, and a python.org framework build on macOS has none until someone
    runs `Install Certificates.command` — so `yeet upgrade` died with
    `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`, which
    reads like GitHub is broken and is nothing of the kind. `requests` carries
    `certifi`'s bundle, and it is already installed on every machine that has
    yeet: docker-py depends on it, and docker-py is a hard dependency.
    """
    try:
        response = requests.get(url, headers=_headers(), timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise UpgradeError(f"could not reach GitHub: {exc}") from exc

    if response.status_code == 404:
        raise UpgradeError("no such release — see " + RELEASES_URL)
    if response.status_code in (403, 429):
        raise UpgradeError(
            "GitHub rate-limited this check. It resets within the hour; "
            "`gh auth login` or $GITHUB_TOKEN raises the limit to 5000/hour."
        )
    if not response.ok:
        raise UpgradeError(f"GitHub answered {response.status_code} {response.reason}")

    try:
        data = response.json()
    except ValueError as exc:
        raise UpgradeError("GitHub returned something that is not JSON") from exc
    if not isinstance(data, dict):
        raise UpgradeError("GitHub returned something that is not a release")
    return data


def _release(tag: str = "") -> tuple[str, str]:
    """`(version, wheel_url)` for `tag`, or for the latest published release.

    A DRAFT release is invisible to `releases/latest` by design, which is the
    behaviour we want: a draft is not shipped, and `yeet upgrade` must never
    hand someone a build its author has not published.
    """
    data = _get_json(API_TAG.format(tag=tag) if tag else API_LATEST)
    version = str(data.get("tag_name", "")).lstrip("v")
    if not version:
        raise UpgradeError("that release has no tag")
    for asset in data.get("assets") or []:
        name = str(asset.get("name", ""))
        if name.endswith(".whl"):
            return version, str(asset.get("browser_download_url", ""))
    raise UpgradeError(f"release v{version} has no wheel attached — install it from {RELEASES_URL}")


# --- comparing ----------------------------------------------------------------


def _parts(version: str) -> tuple[int, ...]:
    """`"0.8.1"` -> `(0, 8, 1)`. Non-numeric pieces sort as 0.

    Deliberately not a full PEP 440 parser: this project tags `v0.8`-shaped
    versions, and pulling in `packaging` to compare two of them would be a
    dependency for one comparison.
    """
    out: list[int] = []
    for piece in version.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def is_newer(candidate: str, current: str) -> bool:
    """Is `candidate` a later version than `current`? Equal lengths not required."""
    left, right = _parts(candidate), _parts(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


# --- where we are installed ---------------------------------------------------


def dev_checkout() -> Path | None:
    """The working tree this yeet runs from, if it is an editable install.

    `pip install -e .` leaves the package importable from the source tree rather
    than from site-packages, and a `pyproject.toml` beside it is the tell. Some
    src-layouts put the package two levels down, hence both parents.
    """
    module = Path(__file__).resolve()
    for parent in module.parents:
        if (parent / "pyproject.toml").is_file() and (parent / ".git").exists():
            return parent
    return None


def _pip_install(url: str) -> None:
    """Into the interpreter running us — which is the venv the installer made."""
    argv = [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", url]
    done = subprocess.run(argv, capture_output=True, check=False)  # noqa: S603
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise UpgradeError("pip could not install it: " + (detail[-1] if detail else "no output"))


# --- the command ---------------------------------------------------------------


def upgrade(
    check: Annotated[
        bool, typer.Option("--check", help="Only report whether a newer version exists.")
    ] = False,
    version: Annotated[
        str | None, typer.Option("--version", help="Install this tag (e.g. v0.8) instead.")
    ] = None,
) -> None:
    """Update yeet in place, from the latest published release.

    `yeet upgrade --check` asks and changes nothing — cheap enough to put in a
    shell startup file. `--version v0.8` pins, which is also how you go back.
    """
    tree = dev_checkout()
    if tree is not None:
        typer.secho(
            f"{SYMBOL_WARN} this is a development checkout at {tree}\n"
            "    `git pull` updates it. Upgrading would replace your working tree "
            "with a published wheel.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(0)

    try:
        target, wheel = _release((version or "").strip())
    except UpgradeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    pinned = bool(version)
    if not pinned and not is_newer(target, __version__):
        typer.secho(f"yeet {__version__} is the latest.", fg=typer.colors.GREEN)
        raise typer.Exit(0)

    change = "installing" if pinned else "upgrading"
    typer.echo(f"{change}: {__version__} -> {target}")
    if check:
        typer.secho(
            f"--check: not installing. `yeet upgrade` does it, or see {RELEASES_URL}",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(0)

    try:
        _pip_install(wheel)
    except UpgradeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        typer.secho(
            f"You can always reinstall from scratch — see {RELEASES_URL}",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(1) from exc

    typer.secho(f"yeet {target} installed. `yeet --version` to confirm.", fg=typer.colors.GREEN)
