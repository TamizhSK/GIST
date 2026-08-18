"""Properties of the install scripts that are invisible in a diff.

The one that prompted this file: `install.sh` lost its executable bit in a
commit whose diff showed no changed lines at all, and `./install.sh` — the
command in the README, in the script's own `--help`, and in CI — became
"permission denied" for everyone who cloned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _index_mode(filename: str) -> str:
    """The mode git RECORDS, not the one this checkout happens to have.

    Checked through the index because that is what a fresh clone gets, and
    because a Windows working tree does not carry a POSIX permission bit for
    `os.access` to read.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-s", "--", filename],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git, or a tarball
        pytest.skip("not a git checkout")
    if not out.strip():  # pragma: no cover - file not tracked
        pytest.skip(f"{filename} is not tracked")
    return out.split()[0]


def test_install_sh_is_executable() -> None:
    """`curl | sh` does not care, but `./install.sh` is the documented way to
    install from a clone and it is the form CI runs."""
    assert _index_mode("install.sh") == "100755", (
        "install.sh must be committed executable — restore it with "
        "`git update-index --chmod=+x install.sh`"
    )


@pytest.mark.parametrize("filename", ["install.sh", "install.ps1"])
def test_the_installers_are_not_empty_and_start_the_way_they_should(filename: str) -> None:
    text = (ROOT / filename).read_text(encoding="utf-8")
    assert len(text) > 1000, f"{filename} looks truncated"
    first = text.splitlines()[0]
    expected = "#!/bin/sh" if filename.endswith(".sh") else "<#"
    assert first.startswith(expected), f"{filename} starts with {first!r}"


def test_install_sh_has_no_crlf() -> None:
    """A `\\r` in the shebang line is `/bin/sh\\r: not found`, which is the
    single most confusing way a shell script can fail."""
    assert b"\r\n" not in (ROOT / "install.sh").read_bytes()
