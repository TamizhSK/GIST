"""B9: semantic checks over the IR — E301/E302/E303/E309/E310/E311/E312.

Position and code are the point: the pipeline gates on errors, and each code
must fire exactly when GitHub would refuse the workflow.

Owner: Dev B
"""

from __future__ import annotations

from conftest import POS, make_job, make_step, make_workflow

from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Strategy
from yeet.validation.layer3_semantic import check, check_secrets


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


# --- E304 / E305 / E306 / E308 / E316 / W318 --------------------------------
#
# The codes that were registered in codes.py and never implemented. Each one
# had a row in the table, a line in docs/rules.md and an entry in
# `yeet explain` — so the tool documented a check it did not perform.


def test_duplicate_step_id_is_e304() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                steps=[make_step(id="setup", run="a"), make_step(id="setup", run="b")],
            )
        }
    )
    assert codes(check(wf)) == ["YEET-E304"]


def test_step_ids_only_have_to_be_unique_within_their_job() -> None:
    wf = make_workflow(
        {
            "a": make_job("a", steps=[make_step(id="setup", run="x")]),
            "b": make_job("b", steps=[make_step(id="setup", run="y")]),
        }
    )
    assert codes(check(wf)) == []


def test_steps_without_an_id_never_collide() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="a"), make_step(run="b")])})
    assert codes(check(wf)) == []


def test_env_name_with_an_equals_sign_is_e305() -> None:
    wf = make_workflow({"build": make_job("build", env={"MY=VAR": "1"})})
    assert codes(check(wf)) == ["YEET-E305"]


def test_step_env_names_are_checked_too() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(run="x", env={"A B": "1"})])})
    assert codes(check(wf)) == ["YEET-E305"]


def test_ordinary_env_names_are_clean() -> None:
    wf = make_workflow({"build": make_job("build", env={"NODE_ENV": "x", "_private": "y"})})
    assert codes(check(wf)) == []


def test_a_dashed_env_name_is_legal() -> None:
    """Regression on the first version of this rule, which used the POSIX
    shell-identifier pattern. `env: {cache-name: ...}` read back as
    `${{ env.cache-name }}` is the example in GitHub's OWN caching docs, and it
    appears 14 times in tests/corpus/curl.yml — the corpus refuted the rule the
    first time it ran against it. The `env` context is a map lookup, not a
    shell export."""
    wf = make_workflow(
        {"build": make_job("build", env={"cache-name": "cache-node-modules", "a.b": "1"})}
    )
    assert codes(check(wf)) == []


def test_uppercase_container_image_is_e306() -> None:
    """Docker rejects it at the daemon, which is a confusing place to learn."""
    wf = make_workflow({"build": make_job("build", container_image="Ubuntu:22.04")})
    assert codes(check(wf)) == ["YEET-E306"]


def test_real_container_images_are_clean() -> None:
    for image in ("node:20", "ghcr.io/org/img:1.2.3", "alpine", "localhost:5000/x/y:dev"):
        wf = make_workflow({"build": make_job("build", container_image=image)})
        assert codes(check(wf)) == [], image


def test_an_expression_as_the_image_is_not_second_guessed() -> None:
    wf = make_workflow({"build": make_job("build", container_image="${{ env.IMAGE }}")})
    assert codes(check(wf)) == []


def test_unpinned_action_is_e308() -> None:
    wf = make_workflow({"build": make_job("build", steps=[make_step(uses="actions/checkout")])})
    bag = check(wf)
    assert codes(bag) == ["YEET-E308"]
    assert "pinned with `@`" in (bag.items[0].help or "")


def test_valid_action_references_are_clean() -> None:
    for ref in (
        "actions/checkout@v4",
        "actions/cache@a1b2c3d",
        "org/repo/sub/action@main",
        "./.yeet/actions/checkout",
        "docker://alpine:3.19",
    ):
        wf = make_workflow({"build": make_job("build", steps=[make_step(uses=ref)])})
        assert codes(check(wf)) == [], ref


def test_an_expression_in_uses_is_only_e312_not_also_e308() -> None:
    """One mistake, one diagnostic. Two codes for one line reads as two bugs."""
    wf = make_workflow({"build": make_job("build", steps=[make_step(uses="${{ env.ACTION }}")])})
    assert codes(check(wf)) == ["YEET-E312"]


def test_runs_on_with_whitespace_is_e316() -> None:
    wf = make_workflow({"build": make_job("build", runs_on="ubuntu latest")})
    assert codes(check(wf)) == ["YEET-E316"]


def test_blank_runs_on_is_e316() -> None:
    wf = make_workflow({"build": make_job("build", runs_on="   ")})
    assert codes(check(wf)) == ["YEET-E316"]


def test_an_unrecognised_runner_label_is_not_a_validation_error() -> None:
    """E315 says so at run time, per job, where the image table is. Refusing
    the whole FILE would stop the linux jobs in it from running too."""
    for label in ("macos-latest", "windows-latest", "self-hosted", "my-arm-box"):
        wf = make_workflow({"build": make_job("build", runs_on=label)})
        assert codes(check(wf)) == [], label


def test_unread_job_output_is_w318() -> None:
    wf = make_workflow({"build": make_job("build", outputs={"sha": "${{ steps.r.outputs.v }}"})})
    assert codes(check(wf)) == ["YEET-W318"]


def test_an_output_a_downstream_job_reads_is_clean() -> None:
    wf = make_workflow(
        {
            "build": make_job("build", outputs={"sha": "${{ steps.r.outputs.v }}"}),
            "deploy": make_job(
                "deploy",
                needs=["build"],
                steps=[make_step(run="deploy ${{ needs.build.outputs.sha }}")],
            ),
        }
    )
    assert codes(check(wf)) == []


def test_a_typo_on_the_reading_side_still_reports_the_unread_output() -> None:
    """The common shape: `outputs: {SHA:}` read as `needs.build.outputs.sha`.
    This is the only check that can see both ends of that mismatch."""
    wf = make_workflow(
        {
            "build": make_job("build", outputs={"SHA": "${{ steps.r.outputs.v }}"}),
            "deploy": make_job(
                "deploy",
                needs=["build"],
                steps=[make_step(run="echo ${{ needs.build.outputs.sha }}")],
            ),
        }
    )
    assert codes(check(wf)) == ["YEET-W318"]


# --- E307: a pure function over names the caller supplies -------------------


def test_missing_secret_is_e307() -> None:
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(run="echo ${{ secrets.NPM_TOKEN }}")])}
    )
    found = check_secrets(wf, set())
    assert [d.code for d in found] == ["YEET-E307"]
    assert "NPM_TOKEN" in found[0].message


def test_a_secret_that_is_set_is_clean() -> None:
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(run="echo ${{ secrets.NPM_TOKEN }}")])}
    )
    assert check_secrets(wf, {"NPM_TOKEN"}) == []


def test_github_token_is_exempt() -> None:
    """GitHub injects it; workflows read it without ever setting it, so
    flagging it would fire on most real files."""
    wf = make_workflow(
        {"build": make_job("build", steps=[make_step(run="echo ${{ secrets.GITHUB_TOKEN }}")])}
    )
    assert check_secrets(wf, set()) == []


def test_each_missing_secret_is_reported_once() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                steps=[
                    make_step(run="a ${{ secrets.TOKEN }}"),
                    make_step(run="b ${{ secrets.TOKEN }}"),
                ],
            )
        }
    )
    assert len(check_secrets(wf, set())) == 1


def test_secrets_in_step_env_and_with_are_seen() -> None:
    wf = make_workflow(
        {
            "build": make_job(
                "build",
                steps=[
                    make_step(run="x", env={"T": "${{ secrets.A }}"}),
                    make_step(uses="./act", with_={"token": "${{ secrets.B }}"}),  # type: ignore[arg-type]
                ],
            )
        }
    )
    assert sorted(d.message for d in check_secrets(wf, set())) == [
        "`secrets.A` is not set",
        "`secrets.B` is not set",
    ]
