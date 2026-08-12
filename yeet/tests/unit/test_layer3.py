"""B9: semantic checks over the IR — E301/E302/E303/E309/E310/E311/E312.

Position and code are the point: the pipeline gates on errors, and each code
must fire exactly when GitHub would refuse the workflow.

Owner: Dev B
"""

from __future__ import annotations

from conftest import POS, make_job, make_step, make_workflow

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Strategy
from yeet.validation.layer3_semantic import check


def codes(bag: DiagnosticBag) -> list[str]:
    return sorted(d.code for d in bag.items)


def test_valid_workflow_is_clean() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                if_="${{ github.event_name == 'push' && "
                "contains(github.event.head_commit.message, '[ci]') }}",
                env={"SHA": "${{ github.sha }}"},
                steps=[
                    make_step(run="echo ${{ toJSON(github.event.pull_request.labels) }}"),
                    make_step(
                        id="test",
                        run="pytest",
                        if_="${{ success() && hashFiles('**/requirements.txt') != '' }}",
                        with_={"args": "${{ fromJSON(github.event.client_payload.extra) }}"},  # type: ignore[arg-type]
                    ),
                ],
            )
        }
    )
    assert codes(check(wf)) == []


def test_unknown_needs_is_e301() -> None:
    wf = make_workflow({"build": make_job("build"), "deploy": make_job("deploy", needs=["buld"])})
    assert codes(check(wf)) == ["YEET-E301"]


def test_each_unknown_needs_gets_its_own_diagnostic() -> None:
    wf = make_workflow({"deploy": make_job("deploy", needs=["a", "b"])})
    assert codes(check(wf)) == ["YEET-E301", "YEET-E301"]


def test_dependency_cycle_is_e302() -> None:
    wf = make_workflow({"a": make_job("a", needs=["b"]), "b": make_job("b", needs=["a"])})
    assert codes(check(wf)) == ["YEET-E302"]


def test_self_cycle_is_e302() -> None:
    wf = make_workflow({"a": make_job("a", needs=["a"])})
    assert codes(check(wf)) == ["YEET-E302"]


def test_cycle_path_is_in_message() -> None:
    wf = make_workflow({"a": make_job("a", needs=["b"]), "b": make_job("b", needs=["a"])})
    (diag,) = check(wf).items
    assert "a -> b -> a" in diag.message


def test_empty_matrix_is_e303() -> None:
    wf = make_workflow({"build": make_job("build", strategy=Strategy(pos=POS))})
    assert codes(check(wf)) == ["YEET-E303"]


def test_exclude_on_undefined_variable_is_e303() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                strategy=Strategy(pos=POS, matrix={"os": ["ubuntu"]}, exclude=[{"version": 18}]),
            )
        }
    )
    assert codes(check(wf)) == ["YEET-E303"]


def test_include_with_new_variables_is_allowed() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                strategy=Strategy(pos=POS, matrix={"os": ["ubuntu"]}, include=[{"version": 18}]),
            )
        }
    )
    assert codes(check(wf)) == []


def test_broken_expression_is_e309() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="echo ${{ foo( }}")])})
    assert codes(check(wf)) == ["YEET-E309"]


def test_empty_expression_is_e309() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="echo ${{ }}")])})
    assert codes(check(wf)) == ["YEET-E309"]


def test_e309_inside_matrix_value() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build", strategy=Strategy(pos=POS, matrix={"version": ["${{ fromJSON( }}"]})
            )
        }
    )
    assert codes(check(wf)) == ["YEET-E309"]


def test_unknown_context_is_e310() -> None:
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(run="echo ${{ githubs.sha }}")])}
    )
    assert codes(check(wf)) == ["YEET-E310"]


def test_unknown_function_is_e311() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="echo ${{ sum(1, 2) }}")])})
    assert codes(check(wf)) == ["YEET-E311"]


def test_function_names_are_case_insensitive() -> None:
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(run="echo ${{ toJSON(fromJSON('[]')) }}")])}
    )
    assert codes(check(wf)) == []


def test_bare_context_ident_is_valid() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="echo ${{ env.FOO }}")])})
    assert codes(check(wf)) == []


def test_uses_with_expression_is_e312() -> None:
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(uses="actions/checkout@${{ 'v4' }}")])}
    )
    assert codes(check(wf)) == ["YEET-E312"]


def test_literal_uses_is_fine() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(uses="actions/checkout@v4")])})
    assert codes(check(wf)) == []


def test_job_level_if_is_checked() -> None:
    wf = make_workflow({"build": make_job("build", if_="${{ githubb.sha }}")})
    assert codes(check(wf)) == ["YEET-E310"]


def test_multiple_expression_errors_are_all_reported() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                if_="${{ foo( }}",
                steps=[make_step(run="echo ${{ bar(1) }}")],
            )
        }
    )
    assert codes(check(wf)) == ["YEET-E309", "YEET-E311"]


def test_source_file_is_attached() -> None:
    wf = make_workflow({"build": make_job("build", needs=["ghost"])})
    (diag,) = check(wf).items
    assert diag.file == wf.source
