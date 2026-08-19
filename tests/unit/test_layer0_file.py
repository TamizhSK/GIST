"""Unit tests for validation/layer0_file.py (Dev D / Task D9)."""

from __future__ import annotations

from pathlib import Path

from yeet.validation.layer0_file import check


def test_layer0_nonexistent_file(tmp_path: Path) -> None:
    bad_path = tmp_path / "nonexistent.yml"
    bag = check(bad_path)
    assert bag.has_errors()
    assert any(d.code == "YEET-E001" for d in bag.items)


def test_layer0_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.yml"
    empty_file.write_bytes(b"")
    bag = check(empty_file)
    assert bag.has_errors()
    assert any(d.code == "YEET-E002" for d in bag.items)


def test_layer0_utf8_bom(tmp_path: Path) -> None:
    bom_file = tmp_path / "bom.yml"
    bom_file.write_bytes(b"\xef\xbb\xbfname: test\n")
    bag = check(bom_file)
    assert any(d.code == "YEET-W004" for d in bag.items)


def test_layer0_uniform_crlf_is_silent(tmp_path: Path) -> None:
    """A plain Windows checkout. Git for Windows ships `core.autocrlf=true`, so
    EVERY file looks like this there — and it cannot bite, because
    `script.write_step_script` normalises to LF before any script reaches a
    shell. W006 fired on every workflow file on every run for a condition
    nobody could act on and nobody needed to."""
    crlf_file = tmp_path / "crlf.yml"
    crlf_file.write_bytes(b"name: test\r\non: push\r\n")
    bag = check(crlf_file)
    assert not any(d.code == "YEET-W006" for d in bag.items)


def test_layer0_mixed_line_endings(tmp_path: Path) -> None:
    """Half-converted by an editor. This one survives into a `run:` scalar."""
    mixed = tmp_path / "mixed.yml"
    mixed.write_bytes(b"name: test\r\non: push\njobs: {}\r\n")
    bag = check(mixed)
    assert any(d.code == "YEET-W006" for d in bag.items)


def test_layer0_pure_lf_is_silent(tmp_path: Path) -> None:
    lf_file = tmp_path / "lf.yml"
    lf_file.write_bytes(b"name: test\non: push\n")
    bag = check(lf_file)
    assert not any(d.code == "YEET-W006" for d in bag.items)


def test_layer0_tab_indentation(tmp_path: Path) -> None:
    tab_file = tmp_path / "tabs.yml"
    tab_file.write_bytes(b"name: test\njobs:\n\tbuild:\n\t\trun: echo hi\n")
    bag = check(tab_file)
    assert bag.has_errors()
    assert any(d.code == "YEET-E005" for d in bag.items)


def test_layer0_non_utf8_bytes(tmp_path: Path) -> None:
    bad_bytes_file = tmp_path / "invalid_utf8.yml"
    bad_bytes_file.write_bytes(b"name: \x80\xff test\n")
    bag = check(bad_bytes_file)
    assert bag.has_errors()
    assert any(d.code == "YEET-E003" for d in bag.items)
