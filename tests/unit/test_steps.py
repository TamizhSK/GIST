"""The step loop, driven by a fake StepExec — no processes, no daemon.

This is where masking, `::add-mask::` and `continue-on-error` are proved. The
same loop runs under Docker, so proving it here proves it there.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from conftest import make_instance, make_job, make_step

from yeet.core.events import STDERR, STDOUT, ListSink
from yeet.core.masking import Masker
from yeet.core.result import Status
from yeet.executor import state_files
from yeet.executor.script import script_suffix
from yeet.executor.steps import Chunk, StepLoopConfig, StepRequest, run_steps
from yeet.executor.workspace import create
from yeet.expressions.contexts import Contexts


class FakeExec:
    """Replays canned output and exit codes, and records what it was asked."""

    def __init__(self, *responses: tuple[int, list[Chunk]]) -> None:
        self.responses = list(responses)
        self.requests: list[StepRequest] = []

    def exec_step(self, request: StepRequest) -> tuple[int, Iterable[Chunk]]:
        self.requests.append(request)
        if not self.responses:
            return 0, []
        return self.responses.pop(0)


def build_config(tmp_path, job, *, masker=None, sink=None):
    layout = create(tmp_path, "run-1")
    return StepLoopConfig(
        job=job,
        job_key=job.key,
        layout=layout.job(job.key),
        root=tmp_path,
        base_env={"CI": "true"},
        masker=masker or Masker(),
        to_step_path=str,
        sink=sink,
        in_container=False,
    )


def out(text: str) -> list[Chunk]:
    return [(STDOUT, text.encode())]


def test_a_passing_step(tmp_path):
    sink = ListSink()
    job = make_job(steps=[make_step("echo hi")])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec((0, out("hi\n"))))

    assert [r.status for r in results] == [Status.SUCCESS]
    assert "hi" in sink.text()


def test_a_failing_step_skips_the_rest(tmp_path):
    job = make_job(steps=[make_step("false"), make_step("echo never"), make_step("echo never")])
    config = build_config(tmp_path, job)

    results = run_steps(config, FakeExec((1, out("boom\n"))))

    assert [r.status for r in results] == [Status.FAILURE, Status.SKIPPED, Status.SKIPPED]
    assert results[0].exit_code == 1


def test_continue_on_error_keeps_going(tmp_path):
    """`delulu: true`."""
    job = make_job(steps=[make_step("false", continue_on_error=True), make_step("echo after")])
    config = build_config(tmp_path, job)

    results = run_steps(config, FakeExec((1, out("")), (0, out("after\n"))))

    assert [r.status for r in results] == [Status.FAILURE, Status.SUCCESS]


def test_secrets_are_masked_before_they_reach_the_sink(tmp_path):
    """Risk #11. One chokepoint — this is the test that guards it."""
    sink = ListSink()
    masker = Masker(["hunter2-the-real-token"])
    job = make_job(steps=[make_step("echo $TOKEN")])
    config = build_config(tmp_path, job, masker=masker, sink=sink)

    run_steps(config, FakeExec((0, out("token is hunter2-the-real-token ok\n"))))

    assert "hunter2-the-real-token" not in sink.text()
    assert "***" in sink.text()


def test_base64_of_a_secret_is_masked_too(tmp_path):
    import base64

    secret = "hunter2-the-real-token"
    encoded = base64.b64encode(secret.encode()).decode()
    sink = ListSink()
    config = build_config(
        tmp_path, make_job(steps=[make_step("x")]), masker=Masker([secret]), sink=sink
    )

    run_steps(config, FakeExec((0, out(f"Authorization: Basic {encoded}\n"))))

    assert encoded not in sink.text()


def test_add_mask_takes_effect_immediately(tmp_path):
    """A token minted at runtime must be redacted from the very next line."""
    sink = ListSink()
    config = build_config(tmp_path, make_job(steps=[make_step("x")]), sink=sink)

    run_steps(
        config,
        FakeExec((0, out("::add-mask::runtime-token-value\nusing runtime-token-value now\n"))),
    )

    assert "runtime-token-value" not in sink.text()
    assert "***" in sink.text()


def test_a_secret_split_across_chunks_is_still_masked(tmp_path):
    """The reason lines are reassembled before masking rather than after."""
    sink = ListSink()
    config = build_config(
        tmp_path, make_job(steps=[make_step("x")]), masker=Masker(["supersecretvalue"]), sink=sink
    )

    run_steps(config, FakeExec((0, [(STDOUT, b"token=supersec"), (STDOUT, b"retvalue done\n")])))

    assert "supersecretvalue" not in sink.text()


def test_streams_stay_apart(tmp_path):
    sink = ListSink()
    config = build_config(tmp_path, make_job(steps=[make_step("x")]), sink=sink)

    run_steps(config, FakeExec((0, [(STDOUT, b"to stdout\n"), (STDERR, b"to stderr\n")])))

    streams = {e.stream: e.text for e in sink.events if e.stream in (STDOUT, STDERR)}
    assert streams[STDOUT] == "to stdout"
    assert streams[STDERR] == "to stderr"


def test_output_without_a_trailing_newline_is_not_lost(tmp_path):
    sink = ListSink()
    config = build_config(tmp_path, make_job(steps=[make_step("x")]), sink=sink)

    run_steps(config, FakeExec((0, [(STDOUT, b"no newline at the end")])))

    assert "no newline at the end" in sink.text()


def test_state_survives_into_the_next_step(tmp_path):
    """Trap #7: step 1 writes FOO=bar to $GITHUB_ENV, step 2 must see it."""
    job = make_job(steps=[make_step("write"), make_step("read")])
    config = build_config(tmp_path, job)

    class WritingExec(FakeExec):
        def exec_step(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                from pathlib import Path

                Path(request.env["GITHUB_ENV"]).write_text("FOO=bar\n")
            return 0, []

    executor = WritingExec()
    run_steps(config, executor)

    assert executor.requests[1].env["FOO"] == "bar"


def test_github_path_is_prepended_for_the_next_step(tmp_path):
    job = make_job(steps=[make_step("write"), make_step("read")])
    config = build_config(tmp_path, job)

    class PathExec(FakeExec):
        def exec_step(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                from pathlib import Path

                Path(request.env["GITHUB_PATH"]).write_text("/opt/tool/bin\n")
            return 0, []

    executor = PathExec()
    run_steps(config, executor)

    assert executor.requests[1].env["PATH"].startswith("/opt/tool/bin")


def test_a_step_name_resolves_its_expressions(tmp_path):
    """`vibe: build ${{ matrix.flavor }}` is how a matrix leg says which leg it
    is. Printed literally, two legs show the same row twice — which is what the
    tree did while the job headers beside it read `build (flavor vanilla)`."""
    sink = ListSink()
    job = make_job(steps=[make_step("echo hi", name="build ${{ matrix.flavor }}")])
    config = build_config(tmp_path, job, sink=sink)
    config.contexts = Contexts(matrix={"flavor": "vanilla"})

    results = run_steps(config, FakeExec((0, out("hi\n"))))

    assert results[0].step_name == "build vanilla"
    assert "${{" not in sink.text()


def test_an_unnamed_step_labels_itself_with_the_resolved_command(tmp_path):
    """The `Run <first line>` fallback expands too, and the trim happens after,
    so the 60 columns are spent on what ran rather than on the expression."""
    job = make_job(steps=[make_step("echo ${{ matrix.flavor }}")])
    config = build_config(tmp_path, job)
    config.contexts = Contexts(matrix={"flavor": "chocolate"})

    results = run_steps(config, FakeExec((0, [])))

    assert results[0].step_name == "Run echo chocolate"


def test_step_outputs_are_collected_by_id(tmp_path):
    job = make_job(steps=[make_step("emit", id="build")])
    config = build_config(tmp_path, job)

    class OutputExec(FakeExec):
        def exec_step(self, request):
            self.requests.append(request)
            from pathlib import Path

            Path(request.env["GITHUB_OUTPUT"]).write_text("version=1.2.3\n")
            return 0, []

    results = run_steps(config, OutputExec())

    assert results[0].outputs == {"version": "1.2.3"}
    assert config.step_outputs["build"] == {"version": "1.2.3"}


def test_both_env_var_names_point_at_the_same_file(tmp_path):
    config = build_config(tmp_path, make_job(steps=[make_step("x")]))
    executor = FakeExec()
    run_steps(config, executor)

    env = executor.requests[0].env
    assert env["GITHUB_ENV"] == env["YEET_ENV"]
    assert env[state_files.ENV_VARS["output"]] == env[state_files.YEET_ALIASES["output"]]


def test_with_becomes_input_env(tmp_path):
    job = make_job(steps=[make_step("x", with_={"node-version": 20})])
    config = build_config(tmp_path, job)
    executor = FakeExec()
    run_steps(config, executor)

    assert executor.requests[0].env["INPUT_NODE_VERSION"] == "20"


def test_group_directives_become_meta_events(tmp_path):
    sink = ListSink()
    config = build_config(tmp_path, make_job(steps=[make_step("x")]), sink=sink)

    run_steps(config, FakeExec((0, out("::group::Installing\nnpm output\n::endgroup::\n"))))

    text = sink.text()
    assert "::group::Installing" in text
    assert "npm output" in text


def test_an_unresolvable_uses_step_is_reported_not_silently_passed(tmp_path):
    """No such action here — skip it, and say which one and why.

    This used to assert the message named `actions.resolver (Dev A, A17)`.
    A17 landed four sessions before anything called it, so the seam outlived
    its blocker and every `uses:` step in every workflow was skipped.
    """
    sink = ListSink()
    job = make_job(steps=[make_step(None, uses="./.yeet/actions/nope")])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec())

    assert results[0].status is Status.SKIPPED
    assert "./.yeet/actions/nope" in sink.text()
    assert "actions.resolver" not in sink.text()


def test_a_docker_action_says_it_is_a_docker_action(tmp_path):
    """C15 is genuinely not built. The message should name the reason, not a
    developer and a ticket that closed."""
    sink = ListSink()
    job = make_job(steps=[make_step(None, uses="docker://alpine:3.19")])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec())

    assert results[0].status is Status.SKIPPED
    assert "docker action" in sink.text()


def test_a_composite_action_runs_its_steps_in_place(tmp_path):
    """The point of A17/A19, unreachable until `uses:` was wired.

    We ship `.yeet/actions/checkout` ourselves so the demo has no external
    dependency; before this, using it did nothing at all.
    """
    action = tmp_path / ".yeet" / "actions" / "greet"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "name: greet\n"
        "inputs:\n"
        "  who:\n"
        "    description: who to greet\n"
        "    default: world\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - run: echo hello $INPUT_WHO\n"
        "    - run: echo second\n",
        encoding="utf-8",
    )

    sink = ListSink()
    job = make_job(steps=[make_step(None, uses="./.yeet/actions/greet", with_={"who": "yeet"})])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec())

    assert [r.status for r in results] == [Status.SUCCESS, Status.SUCCESS]
    assert len(results) == 2, "the composite's two steps each get their own result"


def test_a_composite_step_inherits_continue_on_error(tmp_path):
    action = tmp_path / ".yeet" / "actions" / "flaky"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "name: flaky\nruns:\n  using: composite\n  steps:\n    - run: exit 1\n",
        encoding="utf-8",
    )

    job = make_job(
        steps=[
            make_step(None, uses="./.yeet/actions/flaky", continue_on_error=True),
            make_step("echo after"),
        ]
    )
    config = build_config(tmp_path, job)

    results = run_steps(config, FakeExec((1, out(""))))

    assert results[-1].step_name == "Run echo after", "the run must not stop"


def test_a_backend_exception_fails_the_step_rather_than_the_run(tmp_path):
    sink = ListSink()
    config = build_config(tmp_path, make_job(steps=[make_step("x")]), sink=sink)

    class Broken:
        def exec_step(self, request):
            raise RuntimeError("daemon went away")

    results = run_steps(config, Broken())

    assert results[0].status is Status.FAILURE
    assert "daemon went away" in sink.text()


def test_a_timeout_is_reported_as_124(tmp_path):
    config = build_config(tmp_path, make_job(steps=[make_step("sleep", timeout_minutes=1)]))

    class Slow:
        def exec_step(self, request):
            raise TimeoutError("too slow")

    results = run_steps(config, Slow())

    assert results[0].exit_code == 124
    assert results[0].status is Status.FAILURE


def test_the_script_on_disk_has_no_carriage_returns(tmp_path):
    # `shell` is pinned so the filename is `.sh` on every platform. Left
    # implicit, this test hardcoded `script.sh` while the Windows default
    # resolves to pwsh and `.ps1` — it was asserting the old Windows bug.
    job = make_job(steps=[make_step("echo one\r\necho two", shell="bash")])
    config = build_config(tmp_path, job)
    executor = FakeExec()
    run_steps(config, executor)

    written = (
        tmp_path
        / ".yeet"
        / "tmp"
        / "run-1"
        / "build"
        / "step-1"
        / f"script{script_suffix('bash', in_container=False)}"
    ).read_bytes()
    assert b"\r" not in written


def test_job_result_reports_failure(tmp_path):
    from yeet.executor.steps import build_job_result

    job = make_job(steps=[make_step("false")])
    config = build_config(tmp_path, job)
    results = run_steps(config, FakeExec((1, out(""))))

    result = build_job_result(config, make_instance(job), results, 0.0)
    assert result.status is Status.FAILURE


def test_on_windows_the_script_is_written_where_pwsh_can_run_it(tmp_path, monkeypatch):
    """The Windows regression, at the call site where it actually lived.

    `steps.py` asked `script_suffix(step.shell)` while `shell_argv` applied the
    platform default separately, so a step with no `shell:` was written to
    `script.sh` and invoked as `pwsh -File ...script.sh`. pwsh runs `.ps1` and
    nothing else, so every job on Windows flopped — the whole windows-latest
    leg of the project's first CI run.

    Asserts the two agree: the file that exists is the file argv points at, and
    its extension is one the chosen shell will accept.
    """
    from yeet.executor import script as script_mod

    monkeypatch.setattr(script_mod.platform_, "is_windows", lambda: True)
    monkeypatch.setattr(
        script_mod.shutil, "which", lambda name: "C:/pwsh.exe" if name == "pwsh" else None
    )

    job = make_job(steps=[make_step("echo hi")])
    config = build_config(tmp_path, job)
    executor = FakeExec((0, out("hi\n")))
    run_steps(config, executor)

    argv = executor.requests[0].argv
    assert argv[0] == "pwsh"
    assert argv[-1].endswith(".ps1"), argv
    assert Path(argv[-1]).is_file(), "argv points at a script that was never written"


def test_on_posix_the_pair_is_bash_and_sh(tmp_path, monkeypatch):
    from yeet.executor import script as script_mod

    monkeypatch.setattr(script_mod.platform_, "is_windows", lambda: False)

    job = make_job(steps=[make_step("echo hi")])
    config = build_config(tmp_path, job)
    executor = FakeExec((0, out("hi\n")))
    run_steps(config, executor)

    argv = executor.requests[0].argv
    assert argv[0] == "bash"
    assert argv[-1].endswith(".sh"), argv
    assert Path(argv[-1]).is_file()


# --- the git-auth hint ---------------------------------------------------------
#
# `remote: Invalid username or token` is a true statement that tells the user
# nothing they can act on, because the reason is not in their workflow — it is
# that a container has none of their credentials. See `core/gitcreds.py`.


def err(text: str) -> list[Chunk]:
    return [(STDERR, text.encode())]


AUTH_FAILURE = err(
    "remote: Invalid username or token. Password authentication is not supported "
    "for Git operations.\nfatal: Authentication failed for 'https://github.com/o/r.git/'\n"
)


def test_a_failed_clone_says_why_a_container_could_not_authenticate(tmp_path):
    sink = ListSink()
    job = make_job(steps=[make_step("git clone https://github.com/o/r.git")])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec((128, AUTH_FAILURE)))

    assert results[0].status is Status.FAILURE
    assert "no token was available" in sink.text()
    assert "gh auth login" in sink.text()


def test_the_hint_changes_when_a_token_WAS_passed(tmp_path):
    """ "Give me a token" and "the token you gave me was refused" are different
    bugs with different fixes, and sending someone to re-do a login that
    already worked is worse than saying nothing."""
    sink = ListSink()
    job = make_job(steps=[make_step("git clone https://github.com/o/r.git")])
    config = build_config(tmp_path, job, sink=sink)
    config.base_env["GITHUB_TOKEN"] = "ghp_x"

    run_steps(config, FakeExec((128, AUTH_FAILURE)))

    assert "expired" in sink.text()
    assert "gh auth login" not in sink.text()


def test_a_step_that_merely_mentions_authentication_gets_no_hint(tmp_path):
    """The scan is over git's own vocabulary, not over the word "auth"."""
    sink = ListSink()
    job = make_job(steps=[make_step("./build")])
    config = build_config(tmp_path, job, sink=sink)

    run_steps(config, FakeExec((1, err("error: the authentication module failed to build\n"))))

    assert "gh auth login" not in sink.text()


def test_a_passing_step_never_gets_the_hint(tmp_path):
    """`git fetch` retries and succeeds; the first attempt's noise is not a bug."""
    sink = ListSink()
    job = make_job(steps=[make_step("git fetch || git fetch")])
    config = build_config(tmp_path, job, sink=sink)

    run_steps(config, FakeExec((0, AUTH_FAILURE)))

    assert "gh auth login" not in sink.text()
