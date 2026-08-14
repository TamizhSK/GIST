"""C12 — the build cache is the tag, and C17's prune."""

from __future__ import annotations

from typing import Any

import pytest

from yeet.executor import build
from yeet.executor.images import ImageKind, ImageSpec


@pytest.fixture
def dockerfile(tmp_path):
    path = tmp_path / "Dockerfile"
    path.write_text("FROM ubuntu:22.04\nRUN echo hi\n")
    (tmp_path / "app.py").write_text("print('x')\n")
    return path


class FakeImages:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.built: list[str] = []
        self.removed: list[str] = []

    def get(self, reference: str) -> Any:
        if reference not in self.existing:
            raise KeyError(reference)
        return object()

    def build(self, *, tag: str, **_: Any) -> Any:
        self.built.append(tag)
        self.existing.add(tag)
        return object(), []

    def list(self) -> list[Any]:
        return [type("Img", (), {"tags": [tag]})() for tag in sorted(self.existing)]

    def remove(self, tag: str, force: bool = False) -> None:
        self.existing.discard(tag)
        self.removed.append(tag)


class FakeClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.images = FakeImages(existing)


def test_tag_is_a_valid_docker_reference(dockerfile):
    tag = build.build_tag(dockerfile)
    assert tag.startswith("yeet-local/")
    name, _, digest = tag.partition(":")
    assert len(digest) == build.HASH_LENGTH
    assert " " not in name


def test_tag_is_stable_across_calls(dockerfile):
    assert build.build_tag(dockerfile) == build.build_tag(dockerfile)


def test_tag_changes_when_the_dockerfile_changes(dockerfile):
    before = build.build_tag(dockerfile)
    dockerfile.write_text("FROM alpine\n")
    assert build.build_tag(dockerfile) != before


def test_tag_changes_when_the_context_changes(dockerfile, tmp_path):
    before = build.build_tag(dockerfile)
    (tmp_path / "new_file.txt").write_text("hello")
    assert build.build_tag(dockerfile) != before


def test_excluded_dirs_do_not_affect_the_tag(dockerfile, tmp_path):
    """Otherwise every run rebuilds: .git changes on every commit."""
    before = build.build_tag(dockerfile)
    node_modules = tmp_path / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text("x")
    assert build.build_tag(dockerfile) == before


def test_second_build_is_skipped(dockerfile):
    """That is the whole cache."""
    client = FakeClient()
    spec = ImageSpec(
        kind=ImageKind.BUILD, reference="", dockerfile=dockerfile, context=dockerfile.parent
    )

    first = build.ensure_built(client, spec)
    assert client.images.built == [first]

    second = build.ensure_built(client, spec)
    assert second == first
    assert client.images.built == [first], "an unchanged Dockerfile must not rebuild"


def test_ensure_base_image_is_a_noop_when_present():
    from yeet.executor.images import BASE_IMAGE

    client = FakeClient({BASE_IMAGE})
    assert build.ensure_base_image(client) == BASE_IMAGE
    assert client.images.built == []


def test_ensure_base_image_refuses_to_fall_back(monkeypatch, tmp_path):
    """No silent `ubuntu:22.04` fallback — it would fail three steps later."""
    monkeypatch.setattr(build, "find_base_dockerfile", lambda start=None: None)
    with pytest.raises(FileNotFoundError) as excinfo:
        build.ensure_base_image(FakeClient(), start=tmp_path)
    assert "make image" in str(excinfo.value)


def test_find_base_dockerfile_honours_the_env_override(monkeypatch, tmp_path):
    override = tmp_path / "Dockerfile.base"
    override.write_text("FROM ubuntu:22.04\n")
    monkeypatch.setenv(build.BASE_DOCKERFILE_ENV, str(override))
    assert build.find_base_dockerfile() == override


def test_find_base_dockerfile_finds_the_shipped_one():
    """It has to exist — C4. A missing one makes every ubuntu-latest job fail."""
    found = build.find_base_dockerfile()
    assert found is not None
    assert found.name == "Dockerfile.base"


def test_prune_only_removes_our_images():
    client = FakeClient({"yeet-local/proj:abc123", "node:20", "ubuntu:22.04"})
    removed = build.prune(client)
    assert removed == ["yeet-local/proj:abc123"]
    assert "node:20" in client.images.existing


def test_concurrent_jobs_prepare_one_image_once():
    """A matrix is N jobs and one image. Without the per-reference lock all N
    discover it missing at the same moment and all N build or pull it: the
    daemon serialises the work anyway, so the run pays several times over for
    one image and the log interleaves N copies of the same output."""
    import threading

    from yeet.executor import build as build_mod

    calls: list[str] = []
    notices: list[str] = []
    barrier = threading.Barrier(5)
    present = threading.Event()

    class Client:
        class images:  # noqa: N801 - mirrors the docker SDK's shape
            @staticmethod
            def get(reference):
                if not present.is_set():
                    raise KeyError(reference)
                return object()

    def prepare():
        calls.append("prepared")
        present.set()

    def worker():
        barrier.wait()
        build_mod._prepare_once(Client(), "img:1", prepare, notices.append)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == ["prepared"], "five jobs, one build"
    assert notices == ["img:1"], "and one line about it in the log"


def test_two_projects_with_the_same_directory_name_do_not_share_a_tag(tmp_path):
    """`~/work/api` and `~/oss/api` are different projects. Sharing an image
    repository would mean `yeet prune` in one deletes the other's cache."""
    from yeet.executor.build import project_slug

    a = tmp_path / "work" / "api"
    b = tmp_path / "oss" / "api"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    assert project_slug(a) != project_slug(b)
    assert project_slug(a).startswith("api-")
    assert project_slug(a) == project_slug(a), "and it is stable"
