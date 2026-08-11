"""C13 — real processes on the host. No Docker, no mocks.

These run in `make test`, which means the step loop is exercised end to end on
every commit rather than only when someone has a daemon up.
"""

from __future__ import annotations

import sys

import pytest
from conftest import make_instance, make_job, make_step

from yeet.core.events import ListSink
from yeet.core.masking import Masker
from yeet.core.result import Status
from yeet.executor.backend import JobContext
from yeet.executor.local_backend import LocalBackend
from yeet.executor.runner import RunOptions, run_plan
from yeet.planner.plan import ExecutionPlan

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash steps; pwsh path is separate")


def run_job(tmp_path, job, *, masker=None, sink=None):
    ctx = JobContext(workspace=tmp_path, secrets=masker or Masker(), sink=sink)
    return LocalBackend(tmp_path).run_job(make_instance(job), ctx)


def test_the_walking_skeleton(tmp_path):
    """plan.md 6: `bet: echo "we are so back"`. The seam between subsystems."""
    sink = ListSink()
    job = make_job("build", [make_step('echo "we are so back"')])

    result = run_job(tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS
    assert "we are so back" in sink.text()


def test_three_steps_run_in_order(tmp_path):
    sink = ListSink()
    job = make_job("build", [make_step("echo one"), make_step("echo two"), make_step("echo three")])

    result = run_job(tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS
    assert [r.status for r in result.steps] == [Status.SUCCESS] * 3
    text = sink.text()
    assert text.index("one") < text.index("two") < text.index("three")


def test_a_nonzero_exit_flops_the_job(tmp_path):
    result = run_job(tmp_path, make_job("build", [make_step("exit 3")]))
    assert result.status is Status.FAILURE
    assert result.steps[0].exit_code == 3


def test_set_e_stops_at_the_first_failing_command(tmp_path):
    """`bash -e` — without it a step's real failure is hidden by its last line."""
    sink = ListSink()
    job = make_job("build", [make_step("false\necho SHOULD_NOT_APPEAR")])

    result = run_job(tmp_path, job, sink=sink)

    assert result.status is Status.FAILURE
    assert "SHOULD_NOT_APPEAR" not in sink.text()


def test_state_passes_between_steps(tmp_path):
    """Trap #7, for real: step 1 exports, step 2 reads."""
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step('echo "FOO=bar" >> "$GITHUB_ENV"'),
            make_step('echo "got:$FOO"'),
        ],
    )

    result = run_job(tmp_path, job, sink=sink)

    assert result.status is Status.SUCCESS
    assert "got:bar" in sink.text()


def test_the_yeet_alias_works_too(tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [make_step('echo "VIA=alias" >> "$YEET_ENV"'), make_step('echo "got:$VIA"')],
    )

    assert run_job(tmp_path, job, sink=sink).status is Status.SUCCESS
    assert "got:alias" in sink.text()


def test_multiline_heredoc_state(tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step('printf "BLOB<<EOF\\nline1\\nline2\\nEOF\\n" >> "$GITHUB_ENV"'),
            make_step('echo "got:${BLOB}"'),
        ],
    )

    run_job(tmp_path, job, sink=sink)

    assert "line1" in sink.text()


def test_step_outputs_are_captured(tmp_path):
    job = make_job("build", [make_step('echo "version=1.2.3" >> "$GITHUB_OUTPUT"', id="v")])
    result = run_job(tmp_path, job)
    assert result.steps[0].outputs == {"version": "1.2.3"}


def test_stderr_is_labelled_as_stderr(tmp_path):
    from yeet.core.events import STDERR

    sink = ListSink()
    run_job(tmp_path, make_job("build", [make_step("echo oops >&2")]), sink=sink)

    assert any(e.stream == STDERR and "oops" in e.text for e in sink.events)


def test_secrets_never_reach_the_sink(tmp_path):
    """Risk #11, through a real process this time."""
    sink = ListSink()
    masker = Masker(["s3cret-token-value"])
    job = make_job("build", [make_step('echo "leaking s3cret-token-value here"')])

    run_job(tmp_path, job, masker=masker, sink=sink)

    assert "s3cret-token-value" not in sink.text()
    assert "***" in sink.text()


def test_add_mask_from_a_real_step(tmp_path):
    """A token the step discovers at runtime, redacted from the next line on.

    The step is named so the group header is the name — an unnamed step is
    logged as `Run <first line>`, and that first line is user-authored source
    the Masker has not seen yet. W404 is Dev D's lint for a token hardcoded
    there; masking cannot retroactively cover text it was never told about.
    """
    sink = ListSink()
    job = make_job(
        "build",
        [
            make_step(
                'TOKEN="minted-at-runtime"\necho "::add-mask::$TOKEN"\necho "now $TOKEN"',
                name="mint a token",
            )
        ],
    )

    run_job(tmp_path, job, sink=sink)

    assert "minted-at-runtime" not in sink.text()
    assert "now ***" in sink.text()


def test_working_directory_is_honoured(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "marker.txt").write_text("x")
    sink = ListSink()
    job = make_job("build", [make_step("ls", working_directory="sub")])

    run_job(tmp_path, job, sink=sink)

    assert "marker.txt" in sink.text()


def test_the_workspace_is_the_working_directory(tmp_path):
    (tmp_path / "at_root.txt").write_text("x")
    sink = ListSink()

    run_job(tmp_path, make_job("build", [make_step("ls")]), sink=sink)

    assert "at_root.txt" in sink.text()


def test_ci_is_set(tmp_path):
    sink = ListSink()
    run_job(
        tmp_path, make_job("build", [make_step('echo "CI=$CI GHA=$GITHUB_ACTIONS"')]), sink=sink
    )
    assert "CI=true GHA=true" in sink.text()


def test_env_precedence(tmp_path):
    sink = ListSink()
    job = make_job(
        "build",
        [make_step('echo "v=$SHARED"', env={"SHARED": "from-step"})],
        env={"SHARED": "from-job"},
    )

    run_job(tmp_path, job, sink=sink)

    assert "v=from-step" in sink.text()


def test_timeout_kills_the_process(tmp_path):
    job = make_job("build", [make_step("sleep 30")])
    inst = make_instance(job)
    # timeout_minutes is the user-facing unit; go under it directly for speed.
    job.steps[0].timeout_minutes = 1
    backend = LocalBackend(tmp_path)

    import yeet.executor.steps as steps_mod

    original = steps_mod.StepRequest

    def quick(**kwargs):
        kwargs["timeout_s"] = 0.3
        return original(**kwargs)

    steps_mod.StepRequest = quick  # type: ignore[misc]
    try:
        result = backend.run_job(inst, JobContext(workspace=tmp_path))
    finally:
        steps_mod.StepRequest = original  # type: ignore[misc]

    assert result.status is Status.FAILURE
    assert result.steps[0].exit_code == 124


def test_a_full_plan_through_the_runner(tmp_path):
    """The whole stack minus Docker: plan -> waves -> steps -> RunResult."""
    build = make_instance(make_job("build", [make_step('echo "building"')]))
    deploy = make_instance(make_job("deploy", [make_step('echo "deploying"')], needs=["build"]))
    sink = ListSink()

    result = run_plan(
        ExecutionPlan(waves=[[build], [deploy]]),
        LocalBackend(tmp_path),
        RunOptions(root=tmp_path, workflow_name="hello", sink=sink),
    )

    assert result.status is Status.SUCCESS
    assert result.exit_code == 0
    assert "building" in sink.text()
    assert "deploying" in sink.text()


def test_a_failing_upstream_skips_the_downstream_job_end_to_end(tmp_path):
    build = make_instance(make_job("build", [make_step("exit 1")]))
    deploy = make_instance(
        make_job("deploy", [make_step('echo "SHOULD NOT DEPLOY"')], needs=["build"])
    )
    sink = ListSink()

    result = run_plan(
        ExecutionPlan(waves=[[build], [deploy]]),
        LocalBackend(tmp_path),
        RunOptions(root=tmp_path, workflow_name="gated", sink=sink),
    )

    assert result.exit_code == 1
    assert "SHOULD NOT DEPLOY" not in sink.text()
