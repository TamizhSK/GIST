"""The files the wheel has to contain, and the lookups that read them.

This is where CLI tools die silently: the wheel builds, installs, and then the
primary command fails at run time because a data file was never in it. Both
files below were located by counting `..` from `__file__`, which reaches the
repo root from a checkout and site-packages' parent from an install — so both
worked for the four people who had cloned the repo and for nobody else.

A unit test cannot prove the artifact, and should not pretend to: the dev
install is editable, so `yeet/_data/` does not exist here at all and every
assertion about it would either skip or lie. What is checked here is the part
that CAN be: that the build config force-includes files that exist, and that
the lookup order prefers a checkout. The artifact itself is proven by the
`packaging` job in `.github/workflows/ci.yml`, which builds the wheel,
installs it into a clean venv and runs the two commands that read these files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yeet.cli.cmd_explain import _rules_doc
from yeet.core.resources import packaged_path, packaged_text
from yeet.executor.build import BASE_DOCKERFILE, find_base_dockerfile

try:  # `tomllib` is stdlib from 3.11; 3.10 is in the support matrix.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only on 3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[2]

#: package-relative destination -> the repo file it is copied from
SHIPPED = {"Dockerfile.base": "Dockerfile.base", "rules.md": "docs/rules.md"}


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """A cwd with no repo above it — an installed user in their own project."""
    project = tmp_path / "someones-project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


@pytest.mark.parametrize(("name", "source"), SHIPPED.items())
def test_the_wheel_ships_them(name, source):
    """force-include, so there is one real file and no copy to drift."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert include[source] == f"yeet/_data/{name}"
    assert (ROOT / source).is_file(), f"{source} is force-included but does not exist"


@pytest.mark.parametrize("name", ["Dockerfile.base", "rules.md", "not-shipped.txt"])
def test_the_lookup_answers_instead_of_raising(name):
    """It runs in an editable install, a wheel, and a zip import, and the
    caller's fallback depends on getting None rather than an exception."""
    assert packaged_text(name) is None or isinstance(packaged_text(name), str)
    assert packaged_path(name) is None or packaged_path(name).is_file()


def test_the_base_dockerfile_lookup_reaches_the_package(installed):
    """The failure this replaces: `yeet run` told an installed user to run
    `make image` in a project they had never cloned. From a directory with no
    repo above it, the packaged copy is the only thing left to find — so the
    assertion is that the lookup CONSULTS it, which is testable here, rather
    than that it hits, which is only true once the wheel is built."""
    assert find_base_dockerfile(installed) == packaged_path(BASE_DOCKERFILE)


def test_a_checkout_s_own_dockerfile_still_wins(tmp_path, monkeypatch):
    """Editing `Dockerfile.base` in a checkout has to change what gets built,
    or the packaged copy silently shadows local work."""
    project = tmp_path / "checkout"
    project.mkdir()
    theirs = project / BASE_DOCKERFILE
    theirs.write_text("FROM scratch\n", encoding="utf-8")

    assert find_base_dockerfile(project) == theirs


def test_explain_reads_the_checkout_doc_when_there_is_one():
    """In a checkout the file on disk is the newer one — `make rules` writes it
    and the wheel is built afterwards."""
    doc = _rules_doc()

    assert doc is not None
    assert "YEET-E301" in doc
