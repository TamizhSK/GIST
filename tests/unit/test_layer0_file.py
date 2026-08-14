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


def test_layer0_crlf(tmp_path: Path) -> None:
    crlf_file = tmp_path / "crlf.yml"
    crlf_file.write_bytes(b"name: test\r\non: push\r\n")
    bag = check(crlf_file)
    assert any(d.code == "YEET-W006" for d in bag.items)


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
