"""The per-instance / per-step contexts — executor/contexts.py.

The e2e tripwires in `tests/e2e/test_walking_skeleton.py` prove the wiring
reaches a real step. These cover the decisions inside the functions, which a
subprocess test can only observe indirectly: the copy-don't-mutate rule that
keeps parallel legs apart, the instance-key-to-job-name translation, and the
fact that expressions speak GitHub's vocabulary rather than the console's.
"""

from __future__ import annotations

from yeet.core.diagnostics import Position
from yeet.core.ir import Job
from yeet.core.result import JobResult, Status
from yeet.executor import contexts as ctx_mod
from yeet.expressions.contexts import Contexts
from yeet.planner.plan import JobInstance

POS = Position(line=0, col=0)


def instance(key: str, leg: dict[str, object] | None = None, job_key: str = "") -> JobInstance:
    job = Job(key=job_key or key, pos=POS)
    return JobInstance(job=job, leg=leg or {}, key=key)


def test_for_instance_fills_the_matrix_leg():
    base = Contexts()
    out = ctx_mod.for_instance(base, instance("build (node 18)", {"node": 18}, "build"), {}, {})
    assert out is not None
    assert out.matrix == {"node": 18}


def test_for_instance_never_mutates_the_shared_base():
    """The thread-safety property, asserted directly.

    Jobs in a wave run in parallel threads off one base `Contexts`. If this
    ever starts mutating instead of copying, two legs share a `matrix` dict and
    one of them reads the other's values — intermittently, and only under load.
    """
    base = Contexts()
    a = ctx_mod.for_instance(base, instance("b (node 16)", {"node": 16}, "b"), {}, {})
    b = ctx_mod.for_instance(base, instance("b (node 18)", {"node": 18}, "b"), {}, {})

    assert base.matrix == {}, "the shared base must be left untouched"
    assert a is not base and b is not base
    assert a is not None and b is not None
    assert a.matrix == {"node": 16}
    assert b.matrix == {"node": 18}


def test_none_in_none_out_so_degradation_stays_visible():
    """None means "no expression engine", which `interpolate` reports. An empty
    `Contexts` means "an engine that can see nothing", which it would not."""
    assert ctx_mod.for_instance(None, instance("build"), {}, {}) is None
    assert ctx_mod.for_step(None, env={}, base_env={}, step_outputs={}, step_conclusions={}) is None


def test_needs_is_keyed_by_job_name_not_instance_key():
    """`needs: [build]` names a job; results are keyed `build (node 20)`."""
    upstream = {"build (node 20)": JobResult(job_key="build (node 20)", status=Status.SUCCESS)}
    needs = ctx_mod.needs_context(upstream, {"build (node 20)": "build"})
    assert set(needs) == {"build"}


def test_a_matrix_upstream_collapses_to_one_entry():
    upstream = {
        "build (node 16)": JobResult(
            job_key="build (node 16)", status=Status.SUCCESS, outputs={"a": "1"}
        ),
        "build (node 18)": JobResult(
            job_key="build (node 18)", status=Status.SUCCESS, outputs={"b": "2"}
        ),
    }
    job_of = {"build (node 16)": "build", "build (node 18)": "build"}
    needs = ctx_mod.needs_context(upstream, job_of)
    assert needs["build"]["outputs"] == {"a": "1", "b": "2"}
    assert needs["build"]["result"] == "success"


def test_one_failed_leg_makes_the_whole_dependency_a_failure():
    upstream = {
        "build (node 16)": JobResult(job_key="build (node 16)", status=Status.SUCCESS),
        "build (node 18)": JobResult(job_key="build (node 18)", status=Status.FAILURE),
    }
    job_of = {"build (node 16)": "build", "build (node 18)": "build"}
    assert ctx_mod.needs_context(upstream, job_of)["build"]["result"] == "failure"


def test_expressions_use_githubs_words_not_the_consoles():
    """`slayed`/`flopped` are for the terminal. A real workflow tests
    `needs.build.result == 'success'`, and we promise those files run."""
    upstream = {"build": JobResult(job_key="build", status=Status.FAILURE)}
    assert ctx_mod.needs_context(upstream, {"build": "build"})["build"]["result"] == "failure"
    assert ctx_mod.RESULT_WORDS[Status.SUCCESS] == "success"
    assert ctx_mod.RESULT_WORDS[Status.SKIPPED] == "skipped"
    assert "slayed" not in ctx_mod.RESULT_WORDS.values()


def test_runner_context_follows_the_backend_not_the_host():
    """Read from the env the step will get, so `${{ runner.os }}` and
    `$RUNNER_OS` cannot disagree inside one container."""
    ctx = ctx_mod.runner_context(
        {"RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "RUNNER_TEMP": "/tmp"}
    )
    assert ctx["os"] == "Linux"
    assert ctx["arch"] == "X64"
    assert ctx["temp"] == "/tmp"
    assert ctx["name"] == "yeet"


def test_steps_context_exposes_outputs_and_conclusion():
    ctx = ctx_mod.steps_context({"mk": {"name": "app-1.2.3"}}, {"mk": "success"})
    assert ctx["mk"]["outputs"]["name"] == "app-1.2.3"
    assert ctx["mk"]["conclusion"] == "success"
    assert ctx["mk"]["outcome"] == "success"


def test_for_step_layers_env_over_the_job_contexts():
    job_ctx = ctx_mod.for_instance(
        Contexts(secrets={"T": "x"}), instance("b (n 1)", {"n": 1}, "b"), {}, {}
    )
    step = ctx_mod.for_step(
        job_ctx,
        env={"FOO": "bar"},
        base_env={"RUNNER_OS": "Linux"},
        step_outputs={"mk": {"k": "v"}},
        step_conclusions={"mk": "success"},
    )
    assert step is not None
    assert step.env == {"FOO": "bar"}
    assert step.matrix == {"n": 1}, "the job's matrix must survive the step layer"
    assert step.secrets == {"T": "x"}, "run-wide contexts must survive too"
    assert step.steps["mk"]["outputs"] == {"k": "v"}
