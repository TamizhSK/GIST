"""A container has none of your credentials — `core/gitcreds.py` gives it some.

The two halves are tested separately on purpose: discovery talks to the outside
world (the environment, `gh`, the user's credential helper) and the config
builder is pure. Only the first needs anything faked.
"""

from __future__ import annotations

import pytest

from yeet.core import gitcreds


@pytest.fixture(autouse=True)
def _no_cache() -> None:
    """Discovery caches for the process; a test must not see the last one's answer."""
    gitcreds.reset_cache()


# --- discovery ----------------------------------------------------------------


def test_the_environment_is_read_first_and_in_order() -> None:
    found = gitcreds.discover_token({"GH_TOKEN": "second", "GITHUB_TOKEN": "first"})
    assert found.token == "first"
    assert found.source == "$GITHUB_TOKEN"


def test_a_blank_variable_is_not_a_token() -> None:
    """An exported-but-empty variable is how a shell script says "no"."""
    gitcreds.reset_cache()
    found = gitcreds.discover_token({"GITHUB_TOKEN": "   ", "GH_TOKEN": "real"})
    assert found.token == "real"


def test_the_opt_out_wins_over_everything() -> None:
    found = gitcreds.discover_token({"GITHUB_TOKEN": "x", gitcreds.OPT_OUT_ENV: "1"})
    assert not found
    assert found.token == ""


def test_the_gh_cli_is_asked_when_the_environment_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitcreds, "_from_gh_cli", lambda: gitcreds.Credential("gho_x", "gh"))
    found = gitcreds.discover_token({})
    assert found.token == "gho_x"


def test_no_token_anywhere_is_an_answer_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public repositories need none. "I found nothing" must not raise."""
    monkeypatch.setattr(gitcreds, "_from_gh_cli", lambda: None)
    monkeypatch.setattr(gitcreds, "_from_credential_helper", lambda: None)
    assert not gitcreds.discover_token({})


def test_discovery_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every leg of a matrix asking would be N keychain reads for one answer."""
    calls = []

    def once() -> gitcreds.Credential:
        calls.append(1)
        return gitcreds.Credential("t", "gh")

    monkeypatch.setattr(gitcreds, "_from_gh_cli", once)
    gitcreds.discover_token({})
    gitcreds.discover_token({})
    assert len(calls) == 1


def test_a_probe_that_fails_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitcreds.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(
        gitcreds.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    )
    assert gitcreds._from_gh_cli() is None


# --- the container's git config -----------------------------------------------


def _config(env: dict[str, str]) -> list[tuple[str, str]]:
    """The GIT_CONFIG_* triple-form, back as the pairs it encodes."""
    count = int(env["GIT_CONFIG_COUNT"])
    return [(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"]) for i in range(count)]


def test_the_bind_mount_ownership_fix_applies_with_or_without_a_token() -> None:
    """Without it every `git` command in the workspace fails on dubious ownership."""
    for token in ("", "ghp_x"):
        assert ("safe.directory", "*") in _config(gitcreds.container_git_env(token))


def test_prompts_are_disabled_so_a_private_repo_cannot_hang_the_step() -> None:
    env = gitcreds.container_git_env("")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "never"


def test_ssh_urls_are_rewritten_to_https_because_a_container_has_no_key() -> None:
    pairs = _config(gitcreds.container_git_env(""))
    rewrites = {value for key, value in pairs if key.endswith(".insteadOf")}
    assert rewrites == {"git@github.com:", "ssh://git@github.com/"}


def test_no_token_means_no_credential_helper() -> None:
    keys = [key for key, _ in _config(gitcreds.container_git_env(""))]
    assert not any(key.startswith("credential.") for key in keys)


def test_a_token_installs_a_helper_and_the_token_is_never_a_config_value() -> None:
    """The whole reason the helper exists rather than a URL rewrite.

    A token in a config VALUE turns up in `git config --list`, in git's error
    messages and in any `set -x` trace. In the environment it is a value the
    `Masker` already knows about.
    """
    env = gitcreds.container_git_env("ghp_supersecret")
    pairs = _config(env)
    assert any(key == "credential.https://github.com.helper" for key, _ in pairs)
    assert not any("ghp_supersecret" in value for _, value in pairs)
    assert "ghp_supersecret" not in " ".join(env.values())


def test_the_helper_reads_the_token_at_step_time() -> None:
    """So a step's own `env: GITHUB_TOKEN:` overrides ours, exactly as on GitHub."""
    helper = dict(_config(gitcreds.container_git_env("t")))["credential.https://github.com.helper"]
    assert helper.startswith("!")
    assert "$GITHUB_TOKEN" in helper


def test_only_git_shaped_variables_are_set() -> None:
    """It merges into a user's environment; it must not be able to shadow theirs."""
    for name in gitcreds.container_git_env("t"):
        assert name.startswith(("GIT_", "SSH_", "GCM_", "YEET_")), name


# --- recognising the failure ---------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        # The exact line from the report that started this.
        "remote: Invalid username or token. Password authentication is not supported "
        "for Git operations.",
        "fatal: Authentication failed for 'https://github.com/o/r.git/'",
        "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
        "git@github.com: Permission denied (publickey).",
        "remote: Repository not found.",
    ],
)
def test_git_auth_failures_are_recognised(line: str) -> None:
    assert gitcreds.looks_like_auth_failure(line)


@pytest.mark.parametrize(
    "line",
    [
        "npm ERR! code ELIFECYCLE",
        "error: pathspec 'main' did not match any file(s) known to git",
        "Compilation failed: authentication module missing",
    ],
)
def test_ordinary_failures_are_not_mistaken_for_auth_failures(line: str) -> None:
    assert not gitcreds.looks_like_auth_failure(line)


def test_the_two_hints_send_the_user_to_different_places() -> None:
    """ "Give me a token" and "the token you gave me was refused" are not the same bug."""
    missing = gitcreds.auth_hint(had_token=False)
    refused = gitcreds.auth_hint(had_token=True)
    assert "gh auth login" in missing
    assert "gh auth login" not in refused
    assert "expired" in refused
