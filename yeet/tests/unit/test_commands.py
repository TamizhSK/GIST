"""C10 — workflow command parsing. Runs on every line of output, so it never raises."""

from __future__ import annotations

import pytest

from yeet.executor import commands


@pytest.mark.parametrize(
    ("line", "name", "value"),
    [
        ("::group::Installing", "group", "Installing"),
        ("::endgroup::", "endgroup", ""),
        ("::warning::heads up", "warning", "heads up"),
        ("::notice::fyi", "notice", "fyi"),
        ("::add-mask::supersecret", "add-mask", "supersecret"),
        ("::debug::verbose thing", "debug", "verbose thing"),
    ],
)
def test_simple_directives(line, name, value):
    command = commands.parse_workflow_command(line)
    assert command is not None
    assert (command.name, command.value) == (name, value)
    assert command.is_known


def test_parameters():
    command = commands.parse_workflow_command("::error file=app.js,line=10::Something broke")
    assert command is not None
    assert command.name == "error"
    assert command.value == "Something broke"
    assert command.params == {"file": "app.js", "line": "10"}


def test_escapes_are_decoded():
    """A colon or comma in a message is escaped, or it breaks the delimiters.

    Spaces are NOT escaped — the encoded set is %25 %0D %0A %3A %2C and nothing
    else, so a `%20` in output is a literal the user wrote.
    """
    command = commands.parse_workflow_command("::error::path%3A broken%2C really")
    assert command is not None
    assert command.value == "path: broken, really"


def test_newlines_are_decoded():
    command = commands.parse_workflow_command("::warning::two%0Alines")
    assert command is not None
    assert command.value == "two\nlines"


def test_percent_is_decoded_last():
    command = commands.parse_workflow_command("::notice::100%25 done")
    assert command is not None
    assert command.value == "100% done"


def test_endgroup_without_a_trailing_marker():
    command = commands.parse_workflow_command("::endgroup")
    assert command is not None
    assert command.name == "endgroup"


@pytest.mark.parametrize(
    "line",
    ["ordinary output", "", "   ", "npm WARN deprecated", "a::b", "::", "::  ::x"],
)
def test_non_directives_return_none(line):
    assert commands.parse_workflow_command(line) is None


def test_deprecated_commands_are_recognised():
    """W411 is Dev D's lint; we still parse them so old actions do not break."""
    command = commands.parse_workflow_command("::set-output name=x::1")
    assert command is not None
    assert command.is_deprecated
    assert not command.is_known


def test_leading_whitespace_is_tolerated():
    assert commands.parse_workflow_command("   ::group::indented") is not None
