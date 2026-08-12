"""Rendering for `yeet init`: flows in the Gen-Z dialect, the bundled checkout
action, and the `.gitignore` runtime-state block.

Owner: Dev A
Tier: 7 — may import from: anything
See docs/architecture.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yeet.core.project import Ecosystem

J2_DIR = Path(__file__).with_name("j2")

# `git clone repo-name` collisions and odd tags are worse than a plain name.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

GITIGNORE_BLOCK = """\
# yeet runtime state
.yeet/tmp/
.yeet/runs/
.yeet/.secrets/
"""


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(J2_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.filters["yq"] = _yaml_quote
    return env


def _yaml_quote(value: Any) -> str:
    """Escape a string for placement inside a double-quoted YAML scalar."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def render_flow(name: str, jobs: list[dict[str, Any]], *, dockerfile: bool, docker_tag: str) -> str:
    """One job dict per ecosystem: `key`, `label`, `image`, `commands`."""
    return (
        _env()
        .get_template("main.yml.j2")
        .render(name=name, jobs=jobs, dockerfile=dockerfile, docker_tag=docker_tag)
    )


def render_checkout_action() -> str:
    return _env().get_template("checkout.yml.j2").render()


def gitignore_entries() -> str:
    return GITIGNORE_BLOCK


def default_flow(name: str) -> str:
    """`yeet init` without --auto: a minimal, valid, editable flow."""
    return render_flow(
        name,
        [
            {
                "key": "build",
                "label": "Build & test",
                "image": "ubuntu-latest",
                "commands": [
                    "echo 'edit me — this is your build step'",
                    "echo 'and this is your test step'",
                ],
            }
        ],
        dockerfile=False,
        docker_tag="",
    )


def auto_flow(name: str, ecosystems: list[Ecosystem], *, dockerfile: bool) -> str:
    """`yeet init --auto`: one job per detected ecosystem, from the fingerprint.

    Each ecosystem's `suggested_image` and `default_commands` come straight out
    of `analyzer.markers`. A polyglot repo gets one job per stack, each with
    the zero-dependency checkout first.
    """
    jobs: list[dict[str, Any]] = []
    for eco in ecosystems:
        if not eco.suggested_image:
            continue  # infra (Dockerfile, compose) — handled below
        jobs.append(
            {
                "key": eco.name,
                "label": f"{eco.name} build & test",
                "image": eco.suggested_image,
                "commands": list(eco.default_commands),
            }
        )
    tag = _slug(name) or "app"
    return render_flow(name, jobs, dockerfile=dockerfile, docker_tag=tag)


def _slug(text: str) -> str:
    return _UNSAFE.sub("-", text).strip("-.").lower()
