"""The environment a step actually runs with, assembled in one place.

WHY THIS FILE EXISTS (it is not in plan.md's file list). architecture.md 3.5
passes `environment=base_env` to `containers.create` and never defines
`base_env`; nothing in the repo lists the GITHUB_*/RUNNER_* variables a step
should see. Rather than scatter that decision across two backends, it lives
here. It is a standup item for Dev B, because the names below have to agree
with `expressions/contexts.py` — `github.sha` and `$GITHUB_SHA` must be the
same value or `${{ }}` and `$VAR` disagree inside one step.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yeet.executor import state_files
from yeet.executor.paths import CONTAINER_WORKSPACE
from yeet.executor.platform_ import runner_arch, runner_os

_INPUT_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def base_env(
    *,
    workspace: str,
    run_id: str,
    run_number: int = 1,
    job_key: str,
    event: str = "push",
    runner_temp: str | None = None,
) -> dict[str, str]:
    """The variables every step gets, before anything workflow-specific.

    `CI=true` is the one that matters most in practice: half the tooling in the
    world changes behaviour on it (non-interactive installs, no progress bars,
    no colour), and a runner that omits it produces output nobody can read.
    """
    return {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "YEET": "true",
        "GITHUB_WORKSPACE": workspace,
        "GITHUB_RUN_ID": run_id,
        "GITHUB_RUN_NUMBER": str(run_number),
        "GITHUB_JOB": job_key,
        "GITHUB_EVENT_NAME": event,
        "RUNNER_OS": runner_os(),
        "RUNNER_ARCH": runner_arch(),
        "RUNNER_TEMP": runner_temp or f"{workspace}/.yeet/tmp",
        "YEET_RUN_ID": run_id,
    }


def container_base_env(
    *, run_id: str, job_key: str, event: str, run_number: int = 1
) -> dict[str, str]:
    """`base_env` for inside a container: the workspace is always /workspace.

    RUNNER_OS is hardcoded to Linux because the image is Linux regardless of
    what the host is — a macOS user's step must not be told `RUNNER_OS=macOS`
    and then fail to find `brew`.
    """
    env = base_env(
        workspace=CONTAINER_WORKSPACE,
        run_id=run_id,
        run_number=run_number,
        job_key=job_key,
        event=event,
        runner_temp=f"{CONTAINER_WORKSPACE}/.yeet/tmp",
    )
    env["RUNNER_OS"] = "Linux"
    return env


def github_env(github: dict[str, Any]) -> dict[str, str]:
    """Dev B's `github` context -> the matching GITHUB_* variables.

    Written against the nine fields `build_github_context` promises. Unknown
    keys are ignored rather than exported blindly, so Dev B adding a field to
    the context never leaks a surprise variable into user scripts.
    """
    mapping = {
        "sha": "GITHUB_SHA",
        "ref": "GITHUB_REF",
        "ref_name": "GITHUB_REF_NAME",
        "repository": "GITHUB_REPOSITORY",
        "actor": "GITHUB_ACTOR",
        "event_name": "GITHUB_EVENT_NAME",
        "run_id": "GITHUB_RUN_ID",
        "run_number": "GITHUB_RUN_NUMBER",
    }
    out: dict[str, str] = {}
    for key, name in mapping.items():
        value = github.get(key)
        if value is not None:
            out[name] = str(value)
    return out


def input_env(with_: dict[str, Any]) -> dict[str, str]:
    """`with: {node-version: 20}` -> `INPUT_NODE_VERSION=20`.

    Uppercase, and every run of non-alphanumerics collapses to a single
    underscore — that is GitHub's rule, and actions read the result directly.
    """
    out: dict[str, str] = {}
    for key, value in with_.items():
        name = _INPUT_UNSAFE.sub("_", str(key)).strip("_").upper()
        if name:
            out[f"INPUT_{name}"] = _stringify(value)
    return out


def state_file_env(
    files: dict[str, Path], *, to_path: Callable[[Path], str] | None = None
) -> dict[str, str]:
    """The five state-file variables, each also aliased as `YEET_*`.

    `to_path` converts a host path to the form the step will see. Inside a
    container that is `paths.to_workspace_path`; on the host it is `str`.
    """
    convert: Callable[[Path], str] = to_path if to_path is not None else str
    out: dict[str, str] = {}
    for key, path in files.items():
        rendered = convert(path)
        out[state_files.ENV_VARS[key]] = rendered
        out[state_files.YEET_ALIASES[key]] = rendered
    return out


def merge_path(env: dict[str, str], entries: list[str]) -> None:
    """Prepend `$GITHUB_PATH` entries, in the order the step wrote them.

    Mutates `env` in place because the caller has just built it and there is no
    reason to copy a dict of a hundred strings per step.
    """
    if not entries:
        return
    current = env.get("PATH", "")
    prefix = ":".join(entries)
    env["PATH"] = f"{prefix}:{current}" if current else prefix


def stringify_all(values: dict[str, Any]) -> dict[str, str]:
    """`env:` values arrive from YAML as int/bool/None. Docker wants strings.

    `True` must become `true`, not `True`: a step doing `if [ "$FLAG" = "true" ]`
    is the normal shape, and Python's default repr silently breaks it.
    """
    return {str(key): _stringify(value) for key, value in values.items()}


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)
