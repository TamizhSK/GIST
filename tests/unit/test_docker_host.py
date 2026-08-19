"""Finding the daemon on a machine where `docker ps` works and we said it didn't.

`docker.from_env()` reads `$DOCKER_HOST` and nothing else; the `docker` CLI
reads `docker context`. Colima, Rancher Desktop, Podman, Lima and rootless
dockerd all set up a context and never export the variable — so the daemon is
running, the CLI can see it, and the SDK cannot. These tests are about closing
that gap on each platform, without a daemon anywhere near them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from yeet.executor import backend, platform_


@pytest.fixture
def docker_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated `~/.docker`, so a developer's real one cannot leak in."""
    config = tmp_path / ".docker"
    config.mkdir()
    monkeypatch.setenv("DOCKER_CONFIG", str(config))
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return config


def _write_context(config: Path, name: str, host: str) -> None:
    """A context exactly as the CLI stores it: a hashed dir with a meta.json."""
    meta = config / "contexts" / "meta" / ("0" * 64)
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "meta.json").write_text(
        json.dumps({"Name": name, "Endpoints": {"docker": {"Host": host}}}),
        encoding="utf-8",
    )
    (config / "config.json").write_text(json.dumps({"currentContext": name}), encoding="utf-8")


# --- the docker context -------------------------------------------------------


def test_the_active_context_is_the_first_thing_tried(
    docker_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is what the `docker` CLI itself would use, so it is what we mean."""
    monkeypatch.setattr(platform_, "is_windows", lambda: False)
    _write_context(docker_config, "colima", "unix:///Users/x/.colima/default/docker.sock")
    assert platform_.docker_host_candidates()[0] == "unix:///Users/x/.colima/default/docker.sock"


def test_the_default_context_is_skipped(
    docker_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`default` means "the built-in default", which `from_env()` already tried."""
    monkeypatch.setattr(platform_, "is_windows", lambda: False)
    _write_context(docker_config, "default", "unix:///var/run/docker.sock")
    (docker_config / "config.json").write_text('{"currentContext": "default"}', encoding="utf-8")
    assert platform_._context_host() is None


def test_docker_context_env_overrides_the_config_file(
    docker_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_context(docker_config, "rancher", "unix:///Users/x/.rd/docker.sock")
    monkeypatch.setenv("DOCKER_CONTEXT", "rancher")
    (docker_config / "config.json").write_text('{"currentContext": "other"}', encoding="utf-8")
    assert platform_._context_host() == "unix:///Users/x/.rd/docker.sock"


def test_a_context_naming_something_else_is_not_used(docker_config: Path) -> None:
    """Matched on the recorded Name, not on the directory it happens to be in."""
    _write_context(docker_config, "colima", "unix:///somewhere.sock")
    (docker_config / "config.json").write_text('{"currentContext": "absent"}', encoding="utf-8")
    assert platform_._context_host() is None


@pytest.mark.parametrize("body", ["", "{", "[]", '{"currentContext": null}'])
def test_a_broken_docker_config_is_not_an_error(docker_config: Path, body: str) -> None:
    """This runs on the error path. A traceback about JSON would replace the
    real message — "Docker is not running" — with one about our parser."""
    (docker_config / "config.json").write_text(body, encoding="utf-8")
    assert platform_._context_host() is None


def test_no_docker_directory_at_all_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "nothing"))
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    assert platform_._context_host() is None


# --- per-platform candidates --------------------------------------------------


def test_windows_offers_both_named_pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker Desktop's WSL2 engine, and the older/Windows-containers pipe."""
    monkeypatch.setattr(platform_, "is_windows", lambda: True)
    monkeypatch.setattr(platform_, "_context_host", lambda: None)
    assert platform_.docker_host_candidates() == [
        "npipe:////./pipe/dockerDesktopLinuxEngine",
        "npipe:////./pipe/docker_engine",
    ]


def test_only_sockets_that_exist_are_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Connecting to an absent socket costs a full timeout, and there are eight."""
    monkeypatch.setattr(platform_, "is_windows", lambda: False)
    monkeypatch.setattr(platform_, "_context_host", lambda: None)
    real = tmp_path / "colima.sock"
    real.touch()
    monkeypatch.setattr(platform_, "_socket_candidates", lambda: [tmp_path / "gone.sock", real])
    assert platform_.docker_host_candidates() == [f"unix://{real}"]


def test_candidates_are_deduplicated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The active context is usually ALSO one of the well-known sockets."""
    sock = tmp_path / "docker.sock"
    sock.touch()
    monkeypatch.setattr(platform_, "is_windows", lambda: False)
    monkeypatch.setattr(platform_, "_context_host", lambda: f"unix://{sock}")
    monkeypatch.setattr(platform_, "_socket_candidates", lambda: [sock])
    assert platform_.docker_host_candidates() == [f"unix://{sock}"]


def test_the_runtimes_people_actually_use_are_covered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`as_posix()`, not `str()`. These are POSIX socket paths — Windows never
    reaches this list, because `docker_host_candidates` returns its named pipes
    first — but the test still RUNS on Windows, where `str(Path("/var/run"))`
    renders as `\\var\\run` and the assertion failed on the separator rather
    than on anything it is trying to prove."""
    monkeypatch.setattr(platform_.Path, "home", classmethod(lambda _cls: tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    joined = " ".join(path.as_posix() for path in platform_._socket_candidates())
    for marker in ("/var/run/docker.sock", ".colima", ".rd", ".lima", "podman", "/run/user/1000"):
        assert marker in joined


# --- the client falls through -------------------------------------------------


class _FakeDocker:
    """Just enough docker-py: `from_env` always fails, `DockerClient` is picky."""

    class _Client:
        def __init__(self, works: bool) -> None:
            self._works = works

        def ping(self) -> bool:
            if not self._works:
                raise RuntimeError("connection refused")
            return True

    def __init__(self, working_host: str | None) -> None:
        self.working_host = working_host
        self.tried: list[str] = []

    def from_env(self) -> _Client:
        raise RuntimeError("Error while fetching server API version")

    def DockerClient(self, *, base_url: str, timeout: int) -> _Client:  # noqa: N802 - docker-py's name
        self.tried.append(base_url)
        return self._Client(base_url == self.working_host)


def test_a_candidate_that_answers_is_used_and_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    """`$DOCKER_HOST` is written back so the `docker` BINARY we shell out to
    for the git container lands on the same daemon this client is on."""
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    fake = _FakeDocker("unix:///second.sock")
    monkeypatch.setattr(
        platform_, "docker_host_candidates", lambda: ["unix:///first.sock", "unix:///second.sock"]
    )
    client = backend._try_candidates(fake)
    assert client is not None
    assert fake.tried == ["unix:///first.sock", "unix:///second.sock"]
    assert os.environ["DOCKER_HOST"] == "unix:///second.sock"


def test_no_candidate_answers_means_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_, "docker_host_candidates", lambda: ["unix:///nope.sock"])
    assert backend._try_candidates(_FakeDocker(None)) is None


# --- saying what went wrong ---------------------------------------------------


def test_the_windows_named_pipe_error_is_translated() -> None:
    """The most common Docker failure on the most common desktop OS, which used
    to fall through to the catch-all and print the raw pipe path."""
    exc = RuntimeError(
        'error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.48/info": '
        "open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified."
    )
    assert backend._no_daemon_reason(exc) == "no Docker daemon is listening"


def test_the_posix_missing_socket_error_is_translated() -> None:
    exc = RuntimeError(
        "Error while fetching server API version: ('Connection aborted.', "
        "FileNotFoundError(2, 'No such file or directory'))"
    )
    assert backend._no_daemon_reason(exc) == "no Docker daemon is listening"


def test_permission_is_not_reported_as_absence() -> None:
    """Different problem, completely different fix — the `docker` group."""
    assert "cannot open it" in backend._no_daemon_reason(PermissionError("permission denied"))


def test_windows_access_denied_is_a_permission_problem() -> None:
    assert "cannot open it" in backend._no_daemon_reason(RuntimeError("Access is denied."))


def test_a_pipe_that_dies_mid_run_reads_as_the_daemon_going_away() -> None:
    """Docker Desktop restarting for an update, on Windows, during a step."""
    exc = RuntimeError("open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file")
    assert backend.daemon_is_gone(exc)
