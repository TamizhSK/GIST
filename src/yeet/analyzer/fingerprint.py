"""Detect the stack from marker files so we can pick an image / generate a flow.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# `tomllib` is stdlib from 3.11. On 3.10 — which is what Ubuntu 22.04 LTS
# ships, and therefore what a great many WSL installs have — it does not
# exist, and `tomli` is the same library under its pre-stdlib name. Declared in
# pyproject as a `python_version < "3.11"` dependency, so this fallback is
# always satisfiable rather than a hopeful import.
if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 in CI
    import tomli as tomllib

# A `sys.version_info` branch rather than try/except ImportError: mypy special-
# cases this form and type-checks the arm matching its `python_version`, where
# the try/except form leaves it unable to resolve a 3.11-only stdlib module on
# a 3.10 run and unable to drop the `type: ignore` on a 3.11 one — the same
# no-spelling-is-green-everywhere bind `ctypes.windll` hit in `platform_.py`.

from yeet.analyzer.markers import EXTENSION_MARKERS, MARKERS
from yeet.core.project import Ecosystem


def fingerprint(root: Path) -> list[Ecosystem]:
    """Multiple matches = polyglot project. Return all of them, ranked.

    Read `engines.node` from package.json and `requires-python` from
    pyproject.toml to pin `Ecosystem.version` rather than guessing a tag.

    Entries with an empty suggested image (Dockerfile, docker-compose.yml) are
    infra, not a stack to run — the Dockerfile surfaces as `Project.dockerfile`
    and compose is noted by the scan report, so neither becomes an Ecosystem.
    """
    root = root.expanduser().resolve()
    seen: set[str] = set()
    found: list[Ecosystem] = []

    def add(name: str, marker: Path, image: str, commands: list[str]) -> None:
        if name in seen or not image:
            return
        seen.add(name)
        version = None
        if name == "node" and marker.name == "package.json":
            version = _engines_node(marker)
        elif name == "python" and marker.name == "pyproject.toml":
            version = _requires_python(marker)
        if version and ":" in image:
            image = f"{image.split(':')[0]}:{version}"
        found.append(
            Ecosystem(
                name=name,
                marker=marker,
                suggested_image=image,
                default_commands=list(commands),
                version=version,
            )
        )

    for marker_name, (name, image, commands) in MARKERS.items():
        marker = root / marker_name
        if marker.is_file():
            add(name, marker, image, list(commands))

    for ext, (name, image, commands) in EXTENSION_MARKERS.items():
        matches = sorted(root.glob(f"*{ext}"))
        if matches:
            add(name, matches[0], image, list(commands))

    return found


def _engines_node(package_json: Path) -> str | None:
    """`"engines": {"node": ">=18.20"}` -> `"18"`. Never raises."""
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    engines = data.get("engines") if isinstance(data, dict) else None
    node = engines.get("node") if isinstance(engines, dict) else None
    if not isinstance(node, str):
        return None
    match = re.search(r"\d+", node)
    return match.group(0) if match else None


def _requires_python(pyproject: Path) -> str | None:
    """`[project] requires-python = ">=3.11"` -> `"3.11"`. Never raises."""
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project") if isinstance(data, dict) else None
    requires = project.get("requires-python") if isinstance(project, dict) else None
    if not isinstance(requires, str):
        return None
    match = re.search(r"\d+\.\d+", requires)
    return match.group(0) if match else None
