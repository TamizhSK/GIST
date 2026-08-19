"""Git credentials for a container, which has none of the ones you have.

A container is a fresh machine. No SSH agent, no `~/.gitconfig`, no credential
helper, no keychain, no `gh` login. So the first hand-written

    - run: git clone https://github.com/me/thing.git

inside one meets

    remote: Invalid username or token. Password authentication is not
            supported for Git operations.
    fatal: Authentication failed for 'https://github.com/me/thing.git/'

and the job dies at a command that works on the host every day. On GitHub that
same step works because `$GITHUB_TOKEN` is sitting in the environment and the
runner has already told git to use it. Locally nobody had.

`actions/checkout` was never the whole story — half the real workflows in the
world clone, fetch, `git ls-remote` or `pip install git+https://…` by hand, and
every one of those is the same failure.

**WHAT THIS FILE DOES**, in two halves that are deliberately separate:

* `discover_token()` finds a token the user already has — the environment, then
  the GitHub CLI, then their own git credential helper. It never prompts and
  never stores anything; it only asks the tools that already know.
* `container_git_env()` turns "there is (or is not) a token" into environment
  variables that configure git INSIDE the container.

**WHY THE ENVIRONMENT AND NOT A CONFIG FILE.** `GIT_CONFIG_COUNT` /
`GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n` is git's own way to set configuration
for one process tree without writing a file. Nothing lands in the bind-mounted
working tree, so nothing can be committed by accident and nothing survives the
container. Writing `~/.gitconfig` inside the image would be invisible to the
user and writing the repo's `.git/config` would be editing their checkout.

**WHY THE TOKEN IS NOT IN THE URL.** The obvious trick is
`url.https://x-access-token:TOKEN@github.com/.insteadOf`, and it works — but
the token is then a config VALUE, which means it turns up in `git config
--list`, in git's own error messages, and in any `set -x` trace. The credential
helper below reads `$GITHUB_TOKEN` at the moment git asks for it instead, so
the only place the secret exists is the environment, where the `Masker` is
already watching for it.

Owner: Dev C
Tier: 0 — imports nothing from this package
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

TOKEN_ENV_NAMES = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT")
"""Read in this order. `GITHUB_TOKEN` is what workflows say, `GH_TOKEN` is what
the GitHub CLI exports, `GITHUB_PAT` is what people call it in `.env` files."""

GIT_USERNAME = "x-access-token"
"""GitHub ignores the username for token auth, but git insists on having one,
and this is the name GitHub's own documentation and `actions/checkout` use."""

OPT_OUT_ENV = "YEET_NO_GIT_CREDENTIALS"
"""Set to 1 and nothing here is injected. For someone who wants the container
to be exactly as credential-less as a fresh machine, and for reproducing a
GitHub failure that only happens without a token."""

DISCOVERY_TIMEOUT_S = 10.0
"""`gh auth token` can touch the OS keychain, which on a locked machine can sit
there. A run must not hang on an optional convenience."""

#: Never let git open a prompt. Without this a private repo makes git block on
#: `Username for 'https://github.com':` reading a terminal the container does
#: not have — the step hangs until its timeout and the log says nothing at all.
#: This is the half that applies whether or not a token was found.
NO_PROMPT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "SSH_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
}

_HELPER = (
    "!f() { "
    'if [ "$1" = get ]; then '
    'printf \'username=%s\\npassword=%s\\n\' "$YEET_GIT_USER" "$GITHUB_TOKEN"; '
    "fi; }; f"
)
"""A git credential helper written as a shell function.

git runs a `!`-prefixed helper as `sh -c '<helper> "$@"' <name> <operation>`, so
`$1` is `get`/`store`/`erase`. Only `get` is answered, and it is answered from
`$GITHUB_TOKEN` as it stands AT THAT MOMENT — which means a step that sets its
own `env: GITHUB_TOKEN:` overrides ours for free, exactly as on GitHub.

`store` and `erase` fall through to a silent success rather than an error: git
calls them after every successful authentication, and a helper that fails there
prints a warning on a line that has nothing to do with what the user ran.
"""


@dataclass(frozen=True, slots=True)
class Credential:
    """A token and where it came from. The source is for the log, not for logic."""

    token: str = ""
    source: str = ""

    def __bool__(self) -> bool:
        return bool(self.token)


_cached: Credential | None = None


def reset_cache() -> None:
    """Forget the discovered token. For tests, and for a long-lived process."""
    global _cached
    _cached = None


def discover_token(env: Mapping[str, str] | None = None) -> Credential:
    """A GitHub token this machine already has, or an empty `Credential`.

    Three sources, cheapest first, and the search stops at the first hit:

    1. the environment — `$GITHUB_TOKEN`, `$GH_TOKEN`, `$GITHUB_PAT`,
    2. `gh auth token`, which is where most developers' token actually lives,
    3. `git credential fill`, which asks the user's OWN credential helper (the
       macOS keychain, `libsecret`, Git Credential Manager) for github.com.

    Never prompts, never writes, never raises. A machine with no token at all
    is a completely normal machine — public repositories need none — so "no
    token" is an answer, not a failure.

    Cached for the process: `git credential fill` can hit a keychain, and every
    leg of a matrix asking separately would be N keychain reads for one answer.
    """
    global _cached
    if _cached is not None:
        return _cached
    _cached = _discover(os.environ if env is None else env)
    return _cached


def _discover(env: Mapping[str, str]) -> Credential:
    if env.get(OPT_OUT_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        return Credential()
    for name in TOKEN_ENV_NAMES:
        value = env.get(name, "").strip()
        if value:
            return Credential(value, f"${name}")
    return _from_gh_cli() or _from_credential_helper() or Credential()


def _from_gh_cli() -> Credential | None:
    if shutil.which("gh") is None:
        return None
    out = _capture(["gh", "auth", "token"])
    token = out.strip().splitlines()[0].strip() if out.strip() else ""
    return Credential(token, "the GitHub CLI (`gh auth token`)") if token else None


def _from_credential_helper() -> Credential | None:
    """Ask the user's own helper for github.com, the way git itself would.

    `git credential fill` is the supported entry point and it consults exactly
    the chain the user configured. `GIT_TERMINAL_PROMPT=0` is what keeps it from
    turning into an interactive prompt when no helper has an answer.
    """
    if shutil.which("git") is None:
        return None
    out = _capture(
        ["git", "credential", "fill"],
        stdin="protocol=https\nhost=github.com\n\n",
        env={**os.environ, **NO_PROMPT_ENV},
    )
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "password" and value.strip():
            return Credential(value.strip(), "your git credential helper")
    return None


def _capture(argv: list[str], *, stdin: str = "", env: Mapping[str, str] | None = None) -> str:
    """Run a probe. Any failure at all means "this source has no answer"."""
    try:
        done = subprocess.run(
            argv,
            input=stdin.encode("utf-8"),
            capture_output=True,
            timeout=DISCOVERY_TIMEOUT_S,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.decode("utf-8", "replace")


def container_git_env(token: str = "") -> dict[str, str]:
    """The git configuration every container gets, as environment variables.

    Three things, and the first two apply even with no token at all:

    * **`safe.directory=*`** — the workspace is bind-mounted from the host and
      owned by a uid that does not exist inside the image, so git refuses to
      touch it with "detected dubious ownership in repository at
      '/workspace'". Every `git describe`, `git rev-parse` and `git status` in
      the workflow fails on a message about ownership that is an artefact of
      the mount and nothing to do with the user's repository. `--global` config
      would have to be written into the image; this needs no image at all.
    * **SSH URLs rewritten to HTTPS** — a container has no SSH key and no
      agent, so `git@github.com:owner/repo` cannot work in there under any
      circumstances. Rewritten it works for a public repository immediately and
      for a private one as soon as there is a token. The rewrite carries no
      credentials, so it is safe with or without one.
    * **a credential helper**, only when there is a token to serve.

    Returns a dict the caller merges into the container environment. It sets
    only `GIT_*`, `SSH_ASKPASS`, `GCM_INTERACTIVE` and `YEET_GIT_USER`, so it
    can never shadow anything from the user's workflow.
    """
    entries: list[tuple[str, str]] = [
        ("safe.directory", "*"),
        # Multi-valued on purpose: one `insteadOf` key with two values is how
        # git spells "either of these spellings". Both are in the wild.
        ("url.https://github.com/.insteadOf", "git@github.com:"),
        ("url.https://github.com/.insteadOf", "ssh://git@github.com/"),
    ]
    out = dict(NO_PROMPT_ENV)
    if token:
        entries.append(("credential.https://github.com.helper", _HELPER))
        entries.append(("credential.https://github.com.username", GIT_USERNAME))
        out["YEET_GIT_USER"] = GIT_USERNAME

    out["GIT_CONFIG_COUNT"] = str(len(entries))
    for index, (key, value) in enumerate(entries):
        out[f"GIT_CONFIG_KEY_{index}"] = key
        out[f"GIT_CONFIG_VALUE_{index}"] = value
    return out


#: Lowercased substrings that mean "git could not authenticate", from git and
#: from GitHub's own server-side messages. Matched on text because the exit
#: code is 128 for every fatal git error and says nothing about which one.
AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "password authentication is not supported",
    "support for password authentication was removed",
    "invalid username or token",
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "permission denied (publickey)",
    "please make sure you have the correct access rights",
    "repository not found",
    "remote: not found",
)


def looks_like_auth_failure(text: str) -> bool:
    """Did this line say git could not get in?"""
    lowered = text.lower()
    return any(marker in lowered for marker in AUTH_FAILURE_MARKERS)


def auth_hint(*, had_token: bool) -> str:
    """One line telling the user what to do about it.

    Two different sentences, because "you gave me nothing" and "what you gave
    me was refused" have completely different fixes and printing the first when
    the second is true sends people to re-do a login that already worked.
    """
    if had_token:
        return (
            "git could not authenticate to GitHub, and a token WAS passed in — check that it "
            "has not expired and that it can read that repository (a private one needs the "
            "`repo` scope). `yeet secrets set GITHUB_TOKEN` replaces it."
        )
    return (
        "git could not authenticate to GitHub, and no token was available to pass in. "
        "A container has none of your machine's credentials. Fix it once with `gh auth login`, "
        "or `yeet secrets set GITHUB_TOKEN`, or by exporting $GITHUB_TOKEN."
    )
