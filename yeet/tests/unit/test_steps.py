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


def test_a_uses_step_is_reported_not_silently_passed(tmp_path):
    """Dev A's resolver is not here yet — say so rather than claim success."""
    sink = ListSink()
    job = make_job(steps=[make_step(None, uses="./.yeet/actions/checkout")])
    config = build_config(tmp_path, job, sink=sink)

    results = run_steps(config, FakeExec())

    assert results[0].status is Status.SKIPPED
    assert "actions.resolver" in sink.text()


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
        / f"script{script_suffix(None, in_container=False)}"
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
