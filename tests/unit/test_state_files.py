"""C9 — the file dance that makes state survive between steps (trap #7)."""

from __future__ import annotations

from yeet.executor import state_files


def test_prepare_creates_all_five(tmp_path):
    files = state_files.prepare(tmp_path / "step-1")
    assert set(files) == {"env", "output", "path", "summary", "state"}
    assert all(path.is_file() for path in files.values())


def test_simple_pairs(tmp_path):
    files = state_files.prepare(tmp_path)
    files["env"].write_text("FOO=bar\nBAZ=qux\n")
    back = state_files.read_back(tmp_path)
    assert back["env"] == {"FOO": "bar", "BAZ": "qux"}


def test_a_value_may_contain_equals(tmp_path):
    files = state_files.prepare(tmp_path)
    files["output"].write_text("URL=https://x/?a=1&b=2\n")
    assert state_files.read_back(tmp_path)["output"]["URL"] == "https://x/?a=1&b=2"


def test_heredoc_multiline(tmp_path):
    """A JSON blob or a PEM key in $GITHUB_ENV — a naive parser mangles these."""
    files = state_files.prepare(tmp_path)
    files["env"].write_text("KEY<<EOF\nline one\nline two\nEOF\nAFTER=yes\n")
    back = state_files.read_back(tmp_path)
    assert back["env"]["KEY"] == "line one\nline two"
    assert back["env"]["AFTER"] == "yes"


def test_heredoc_with_a_custom_delimiter(tmp_path):
    files = state_files.prepare(tmp_path)
    files["env"].write_text("CERT<<ghdelimiter\n-----BEGIN-----\nghdelimiter\n")
    assert state_files.read_back(tmp_path)["env"]["CERT"] == "-----BEGIN-----"


def test_path_keeps_write_order(tmp_path):
    files = state_files.prepare(tmp_path)
    files["path"].write_text("/opt/first\n/opt/second\n\n/opt/third\n")
    back = state_files.read_back(tmp_path)
    assert state_files.path_entries(back) == ["/opt/first", "/opt/second", "/opt/third"]


def test_summary_is_raw_text(tmp_path):
    files = state_files.prepare(tmp_path)
    files["summary"].write_text("# Results\n\nAll good.\n")
    assert "# Results" in state_files.read_back(tmp_path)["summary"]["text"]


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    files = state_files.prepare(tmp_path)
    files["env"].write_text("GOOD=1\nthis is not a pair\n=novalue\nALSO_GOOD=2\n")
    back = state_files.read_back(tmp_path)
    assert back["env"] == {"GOOD": "1", "ALSO_GOOD": "2"}


def test_missing_directory_reads_empty(tmp_path):
    back = state_files.read_back(tmp_path / "never-created")
    assert back["env"] == {}
    assert back["summary"]["text"] == ""


# --- what PowerShell actually writes ----------------------------------------
# Windows PowerShell 5.1's default output encoding is UTF-16 ("Unicode"), so
# `"k=v" >> $env:GITHUB_OUTPUT` in a `cooked_on: local` step on Windows lands on
# disk as UTF-16. Read as UTF-8 that parsed into a key nobody could ever
# reference, so the step went green with an output that was silently empty.


def test_utf16_le_with_a_bom_is_read(tmp_path):
    """The FIRST write from PowerShell 5.1: BOM, then UTF-16 LE."""
    files = state_files.prepare(tmp_path)
    files["output"].write_bytes(b"\xff\xfe" + "baked=vanilla\r\n".encode("utf-16-le"))
    assert state_files.read_back(tmp_path)["output"] == {"baked": "vanilla"}


def test_utf16_le_without_a_bom_is_read(tmp_path):
    """The appends AFTER it: `>>` onto an existing file repeats no BOM, so the
    NUL pattern is the only evidence left."""
    files = state_files.prepare(tmp_path)
    files["output"].write_bytes("baked=vanilla\r\nlayer=two\r\n".encode("utf-16-le"))
    assert state_files.read_back(tmp_path)["output"] == {"baked": "vanilla", "layer": "two"}


def test_utf16_be_without_a_bom_is_read(tmp_path):
    files = state_files.prepare(tmp_path)
    files["env"].write_bytes("FOO=bar\n".encode("utf-16-be"))
    assert state_files.read_back(tmp_path)["env"] == {"FOO": "bar"}


def test_utf8_with_a_bom_loses_the_bom_not_the_key(tmp_path):
    """A UTF-8 BOM is what `Set-Content -Encoding UTF8` writes in 5.1. Left in
    place it becomes part of the first key's name."""
    files = state_files.prepare(tmp_path)
    files["output"].write_bytes(b"\xef\xbb\xbf" + b"baked=vanilla\n")
    assert state_files.read_back(tmp_path)["output"] == {"baked": "vanilla"}


def test_plain_utf8_is_still_plain_utf8(tmp_path):
    """The sniffing must not cost the common case: bash writes UTF-8, including
    non-ASCII, and it has no BOM and no NULs."""
    files = state_files.prepare(tmp_path)
    files["output"].write_bytes("emoji=✅ done\nname=café\n".encode())
    assert state_files.read_back(tmp_path)["output"] == {"emoji": "✅ done", "name": "café"}


def test_yeet_aliases_cover_every_file():
    assert set(state_files.YEET_ALIASES) == set(state_files.ENV_VARS)
    assert state_files.YEET_ALIASES["env"] == "YEET_ENV"
    assert state_files.YEET_ALIASES["summary"] == "YEET_STEP_SUMMARY"
