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


def test_invalid_env_name_is_e305() -> None:
    wf = make_workflow({"build": make_job("build", env={"1BAD": "x"})})
    assert codes(check(wf)) == ["YEET-E305"]


def test_invalid_container_image_is_e306() -> None:
    wf = make_workflow({"build": make_job("build", container_image="Ubuntu")})
    assert codes(check(wf)) == ["YEET-E306"]


def test_missing_secret_is_e307() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="echo ${{ secrets.MISSING }}")])})
    assert codes(check(wf)) == ["YEET-W317"]


def test_matrix_undeclared_var_is_e308() -> None:
    wf = make_workflow({
        "build": make_job(
            "build",
            strategy=Strategy(pos=POS, matrix={"os": ["ubuntu"]}),
            steps=[make_step(run="echo ${{ matrix.NONEXISTENT }}")],
        )
    })
    assert codes(check(wf)) == ["YEET-E308"]


def test_duplicate_job_name_is_e304() -> None:
    a = make_job("a", name="same")
    b = make_job("b", name="same")
    wf = make_workflow({"a": a, "b": b})
    assert codes(check(wf)) == ["YEET-E304"]


def test_unused_output_is_w318() -> None:
    wf = make_workflow({"build": make_job("build", outputs={"out": "x"})})
    assert codes(check(wf)) == ["YEET-W318"]


def test_local_uses_without_action_is_e313(project_root: Path) -> None:
    # create an empty directory to simulate a local action without action.yml
    (project_root / "noaction").mkdir()
    wf = make_workflow({"build": make_job("build", steps=[make_step(uses="./noaction")])})
    wf.source = project_root / "flow.yml"
    codeset = codes(check(wf))
    assert "YEET-W313" in codeset


def test_action_missing_required_input_is_e314(project_root: Path) -> None:
    # create a minimal action.yml that requires input `foo`
    action_dir = project_root / "actionreq"
    action_dir.mkdir()
    yml = action_dir / "action.yml"
    yml.write_text(
        """
inputs:
  foo:
    required: true
runs:
  using: composite
  steps:
    - run: echo hi
""",
        encoding="utf-8",
    )
    wf = make_workflow({"build": make_job("build", steps=[make_step(uses="./actionreq")])})
    wf.source = project_root / "flow.yml"
    codeset = codes(check(wf))
    assert "YEET-E314" in codeset
