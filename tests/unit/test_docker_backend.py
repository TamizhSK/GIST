"""C8 — real containers. `make docker`, skipped without a daemon.

The Day-2 ship target lives here: three steps, one container, state carried
between them. Everything else in the suite proves the loop; this proves the
loop is wired to Docker correctly.
"""

from __future__ import annotations

import pytest
from conftest import make_instance, make_job, make_step

from yeet.core.events import ListSink
from yeet.core.masking import Masker
from yeet.core.result import Status
from yeet.executor.backend import JobContext
from yeet.executor.docker_backend import _LIVE, CONTAINER_PREFIX, DockerBackend
from yeet.executor.runner import RunOptions, run_plan
from yeet.planner.plan import ExecutionPlan

pytestmark = pytest.mark.docker

IMAGE = "ubuntu:22.04"
"""These tests pin a plain image rather than resolving `ubuntu-latest`, so they
exercise the backend without first requiring `make image`. The base-image path
has its own test below."""


@pytest.fixture
def backend(docker_client, tmp_path):
    return DockerBackend(tmp_path, client=docker_client)


def run(backend, tmp_path, job, *, masker=None, sink=None):
    ctx = JobContext(workspace=tmp_path, secrets=masker or Masker(), sink=sink)
    return backend.run_job(make_instance(job), ctx)


def test_three_steps_in_one_container(backend, tmp_path):
    """THE Day-2 ship target."""
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step('echo "we are so back"'),
            make_step("echo step two"),
            make_step("echo step three"),
        ],
        container_image=IMAGE,
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS
    assert [step.status for step in result.steps] == [Status.SUCCESS] * 3
    assert "we are so back" in sink.text()


def test_state_survives_between_steps_in_the_container(backend, tmp_path):
    """The whole reason for one container per job."""
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step('echo "FOO=bar" >> "$GITHUB_ENV"'),
            make_step('echo "got:$FOO"'),
        ],
        container_image=IMAGE,
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS
    assert "got:bar" in sink.text()


def test_filesystem_state_survives_between_steps(backend, tmp_path):
    """A `docker run` per step would lose this — installed packages, cwd, files."""
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step("mkdir -p /tmp/marker && echo hi > /tmp/marker/f"),
            make_step("cat /tmp/marker/f"),
        ],
        container_image=IMAGE,
    )

    assert run(backend, tmp_path, job, sink=sink).status is Status.SUCCESS
    assert "hi" in sink.text()


def test_a_failing_step_reports_its_real_exit_code(backend, tmp_path):
    """THE trap: `exec_run(stream=True)` returns exit_code=None, and a naive
    implementation would report this step as passing."""
    job = make_job("build", [make_step("exit 42")], container_image=IMAGE)

    result = run(backend, tmp_path, job)

    assert result.status is Status.FAILURE
    assert result.steps[0].exit_code == 42


def test_a_failing_step_stops_the_rest(backend, tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [make_step("false"), make_step('echo "SHOULD NOT RUN"')],
        container_image=IMAGE,
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert [s.status for s in result.steps] == [Status.FAILURE, Status.SKIPPED]
    assert "SHOULD NOT RUN" not in sink.text()


def test_the_workspace_is_mounted(backend, tmp_path):
    (tmp_path / "hello.txt").write_text("from the host\n")
    sink = ListSink()
    job = make_job("build", [make_step("cat /workspace/hello.txt")], container_image=IMAGE)

    assert run(backend, tmp_path, job, sink=sink).status is Status.SUCCESS
    assert "from the host" in sink.text()


def test_the_mount_is_writable_and_visible_on_the_host(backend, tmp_path):
    job = make_job("build", [make_step("echo written > /workspace/out.txt")], container_image=IMAGE)

    assert run(backend, tmp_path, job).status is Status.SUCCESS
    assert (tmp_path / "out.txt").read_text().strip() == "written"


def test_secrets_are_masked_from_container_output(backend, tmp_path):
    sink = ListSink()
    masker = Masker(["container-secret-value"])
    job = make_job(
        "build", [make_step('echo "leak container-secret-value"')], container_image=IMAGE
    )

    run(backend, tmp_path, job, masker=masker, sink=sink)

    assert "container-secret-value" not in sink.text()
    assert "***" in sink.text()


def test_stderr_is_separated(backend, tmp_path):
    """demux=True. Without it both streams arrive interleaved and unlabelled."""
    from yeet.core.events import STDERR, STDOUT

    sink = ListSink()
    job = make_job("build", [make_step("echo to-out; echo to-err >&2")], container_image=IMAGE)

    run(backend, tmp_path, job, sink=sink)

    out = {e.text for e in sink.events if e.stream == STDOUT}
    err = {e.text for e in sink.events if e.stream == STDERR}
    assert "to-out" in out
    assert "to-err" in err


def test_no_carriage_returns_reach_bash(backend, tmp_path):
    """Trap #1. A CRLF script dies with `$'\\r': command not found`."""
    job = make_job("build", [make_step("echo one\r\necho two")], container_image=IMAGE)
    assert run(backend, tmp_path, job).status is Status.SUCCESS


def test_the_container_is_removed_afterwards(backend, tmp_path, docker_client):
    job = make_job("build", [make_step("true")], container_image=IMAGE)
    run(backend, tmp_path, job)

    names = [name for c in docker_client.containers.list(all=True) for name in c.name.split()]
    assert not any(name.startswith(f"{CONTAINER_PREFIX}-build-") for name in names)
    assert _LIVE == {}, "the live-container registry must be empty after a run"


def test_the_container_is_removed_even_when_a_step_fails(backend, tmp_path, docker_client):
    job = make_job("build", [make_step("exit 1")], container_image=IMAGE)
    run(backend, tmp_path, job)
    assert _LIVE == {}


def test_workflow_commands_round_trip_through_a_container(backend, tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [make_step('echo "::group::Installing"\necho inside\necho "::endgroup::"')],
        container_image=IMAGE,
    )

    run(backend, tmp_path, job, sink=sink)

    assert "::group::Installing" in sink.text()
    assert "inside" in sink.text()


def test_add_mask_inside_a_container(backend, tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step(
                'T="runtime-container-token"\necho "::add-mask::$T"\necho "using $T"',
                name="mint",
            )
        ],
        container_image=IMAGE,
    )

    run(backend, tmp_path, job, sink=sink)

    assert "runtime-container-token" not in sink.text()


def test_ci_and_workspace_are_set_in_the_container(backend, tmp_path):
    sink = ListSink()
    job = make_job(
        "build", [make_step('echo "$CI|$GITHUB_WORKSPACE|$RUNNER_OS"')], container_image=IMAGE
    )

    run(backend, tmp_path, job, sink=sink)

    assert "true|/workspace|Linux" in sink.text()


def test_a_multi_job_plan_through_the_runner(backend, tmp_path):
    """analyze -> plan -> run, minus the parts other devs own."""
    build = make_instance(make_job("build", [make_step('echo "building"')], container_image=IMAGE))
    deploy = make_instance(
        make_job("deploy", [make_step('echo "deploying"')], needs=["build"], container_image=IMAGE)
    )
    sink = ListSink()

    result = run_plan(
        ExecutionPlan(waves=[[build], [deploy]]),
        backend,
        RunOptions(root=tmp_path, workflow_name="ship it fr fr", sink=sink),
    )

    assert result.status is Status.SUCCESS
    assert "building" in sink.text()
    assert "deploying" in sink.text()


def test_e315_fails_the_job_without_creating_a_container(backend, tmp_path):
    sink = ListSink()
    job = make_job("build", [make_step("true")], runs_on="windows-latest")

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.FAILURE
    assert "YEET-E315" in sink.text()
    assert _LIVE == {}


@pytest.mark.slow
def test_the_base_image_resolves_and_has_the_tools(backend, tmp_path):
    """C4. `ubuntu-latest` must give a container with git, curl, jq and node —
    the whole reason Dockerfile.base exists (trap #3). Builds it if absent."""
    sink = ListSink()
    job = make_job(
        "build",
        [make_step("git --version && curl --version | head -1 && jq --version && node --version")],
        runs_on="ubuntu-latest",
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS, sink.text()
    assert "git version" in sink.text()


# --- git inside the container --------------------------------------------------
#
# A container is a fresh machine: no SSH agent, no ~/.gitconfig, no credential
# helper, no keychain. Three separate failures fall out of that, and all three
# reached the user as git's own words about something else. See
# `core/gitcreds.py`.
#
# `runs_on="ubuntu-latest"` (and so `@slow`) rather than the plain `ubuntu:22.04`
# the rest of this file pins: these are tests ABOUT git, and stock ubuntu has
# none. The base image is also what a real `yeet run` uses, so this is the
# configuration the fix has to hold in.


@pytest.mark.slow
def test_git_can_read_the_bind_mounted_repository(backend, tmp_path):
    """`safe.directory`. The mount is owned by a uid that does not exist inside
    the image, so without this every `git` command in the workspace dies on
    "detected dubious ownership" — a fact about our mount, not their repo."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sink = ListSink()
    job = make_job(
        "build", [make_step("git rev-parse --is-inside-work-tree")], runs_on="ubuntu-latest"
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS, sink.text()
    assert "dubious ownership" not in sink.text()


@pytest.mark.slow
def test_a_clone_without_credentials_fails_fast_instead_of_hanging(backend, tmp_path):
    """`GIT_TERMINAL_PROMPT=0`. Without it git blocks on `Username for
    'https://github.com':` against a terminal the container does not have, and
    the step sits there until its timeout with nothing at all in the log."""
    sink = ListSink()
    job = make_job(
        "build",
        [make_step("git clone https://github.com/yeet-no-such-owner/private.git 2>&1 || true")],
        runs_on="ubuntu-latest",
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS  # `|| true` — the message is the subject
    text = sink.text()
    assert "terminal prompts disabled" in text or "could not read Username" in text


@pytest.mark.slow
def test_the_credential_helper_answers_with_the_job_token(backend, tmp_path):
    """The manual-checkout fix. `git credential fill` is what git itself runs
    before every fetch, so an answer here is an answer for `clone`, `fetch`,
    `ls-remote` and `pip install git+https://…` alike."""
    sink = ListSink()
    job = make_job(
        "build",
        [make_step("printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill")],
        runs_on="ubuntu-latest",
    )
    ctx = JobContext(
        workspace=tmp_path, secrets=Masker(), sink=sink, env={"GITHUB_TOKEN": "ghp_fake"}
    )

    result = backend.run_job(make_instance(job), ctx)

    assert result.status is Status.SUCCESS, sink.text()
    assert "username=x-access-token" in sink.text()


@pytest.mark.slow
def test_the_token_never_reaches_the_git_config(backend, tmp_path):
    """It is served from the environment by a helper precisely so that it is
    never a config VALUE — `git config --list` is somewhere people paste from."""
    sink = ListSink()
    job = make_job("build", [make_step("git config --list || true")], runs_on="ubuntu-latest")
    ctx = JobContext(
        workspace=tmp_path, secrets=Masker(), sink=sink, env={"GITHUB_TOKEN": "ghp_fake_value"}
    )

    backend.run_job(make_instance(job), ctx)

    assert "ghp_fake_value" not in sink.text()


@pytest.mark.slow
def test_an_ssh_url_is_rewritten_so_a_public_repo_still_clones(backend, tmp_path):
    """A container has no SSH key and no agent, so `git@github.com:` cannot work
    in there under any circumstances. Rewritten to HTTPS it does."""
    sink = ListSink()
    job = make_job(
        "build",
        [make_step("git ls-remote git@github.com:octocat/Hello-World.git HEAD")],
        runs_on="ubuntu-latest",
    )

    result = run(backend, tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS, sink.text()
    assert "Permission denied (publickey)" not in sink.text()
