"""C11 — the resolution table from architecture.md 3.5. All four rows, plus E315."""

from __future__ import annotations

import pytest
from conftest import make_job

from yeet.core.project import Project
from yeet.executor.images import (
    BASE_IMAGE,
    ImageKind,
    ImageResolutionError,
    resolve_image,
)


@pytest.fixture
def project(tmp_path):
    return Project(root=tmp_path)


@pytest.mark.parametrize("label", ["ubuntu-latest", "ubuntu-22.04", "UBUNTU-LATEST"])
def test_ubuntu_labels_resolve_to_our_base_image(project, label):
    """Not plain `ubuntu:22.04` — that image has no git, curl or node (trap #3)."""
    spec = resolve_image(make_job(runs_on=label), project)
    assert spec.kind is ImageKind.BASE
    assert spec.reference == BASE_IMAGE


@pytest.mark.parametrize("image", ["node:20", "ghcr.io/org/img:sha", "python:3.12-slim"])
def test_image_tags_are_pulled(project, image):
    spec = resolve_image(make_job(runs_on=image), project)
    assert spec.kind is ImageKind.PULL
    assert spec.reference == image


@pytest.mark.parametrize("label", ["local", "native", "host"])
def test_local_means_no_container(project, label):
    spec = resolve_image(make_job(runs_on=label), project)
    assert spec.kind is ImageKind.LOCAL
    assert spec.needs_container is False


def test_dockerfile_path_is_built(tmp_path, project):
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:22.04\n")
    spec = resolve_image(make_job(runs_on="./Dockerfile"), project)
    assert spec.kind is ImageKind.BUILD
    assert spec.dockerfile == tmp_path / "Dockerfile"
    assert spec.context == tmp_path


def test_auto_detect_when_no_cooked_on(tmp_path):
    """The stated requirement: a repo with only a Dockerfile just works."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ubuntu:22.04\n")
    project = Project(root=tmp_path, dockerfile=dockerfile)

    spec = resolve_image(make_job(runs_on=None), project)
    assert spec.kind is ImageKind.BUILD
    assert spec.note is not None
    assert "no cooked_on set" in spec.note
    assert "building" in spec.note


def test_explicit_container_image_wins(project):
    spec = resolve_image(make_job(runs_on="ubuntu-latest", container_image="node:20"), project)
    assert spec.kind is ImageKind.PULL
    assert spec.reference == "node:20"


def test_dockerfile_key_beats_everything(tmp_path, project):
    (tmp_path / "custom.Dockerfile").write_text("FROM alpine\n")
    job = make_job(
        runs_on="ubuntu-latest", container_image="node:20", dockerfile="custom.Dockerfile"
    )
    assert resolve_image(job, project).kind is ImageKind.BUILD


def test_e315_when_nothing_resolves(project):
    with pytest.raises(ImageResolutionError) as excinfo:
        resolve_image(make_job(runs_on="windows-latest"), project)
    diagnostic = excinfo.value.diagnostic
    assert diagnostic.code == "YEET-E315"
    assert "windows-latest" in diagnostic.message
    assert diagnostic.help is not None


def test_e315_when_there_is_nothing_at_all(project):
    with pytest.raises(ImageResolutionError) as excinfo:
        resolve_image(make_job(runs_on=None), project)
    assert excinfo.value.diagnostic.code == "YEET-E315"


def test_e315_for_a_missing_dockerfile(project):
    with pytest.raises(ImageResolutionError) as excinfo:
        resolve_image(make_job(runs_on="./nope/Dockerfile"), project)
    assert "not found" in excinfo.value.diagnostic.message


def test_e315_is_a_registered_code():
    """docs/rules.md is generated from codes.py — an unregistered code breaks it."""
    from yeet.core.codes import get

    assert get("E315").layer == 3
