"""`uses:` -> local composite | docker | node. Cache under ~/.yeet/actions.

Owner: Dev A
Tier: 2 — may import from: core, expressions, reporting
NOTE: resolves `uses:` into IR only. The EXECUTOR runs it — see plan.md 3.3.
See docs/architecture.md

Contract (plan.md §4, shared with the executor):
    ResolvedAction(kind="composite"|"docker"|"node", steps=[Step, ...],
                   image=None, entrypoint=None, inputs={name: InputSpec},
                   action_dir=Path)

    resolve(uses, root, bag) -> ResolvedAction | None
    resolve_remote(uses, bag) -> ResolvedAction | None   # A20, stretch

A17 scope is Tier 1 (local composite). Docker and node metadata are still
resolved so a `uses:` pointing at one isn't an error — the executor decides
whether it can run them (C15/C16). A20 adds `owner/repo@ref`, shallow-cloned
into `~/.yeet/actions/<owner>/<repo>/<ref>/`, cached by ref.

E313 — `uses:` points at a path that can't be satisfied: a local directory
       that doesn't exist, an `action.yml` that's missing/invalid, or a
       remote ref that fails to clone.
E314 — required input not supplied in `with:` (emitted by apply_inputs).
W319 — `with:` supplies an input the action.yml doesn't declare (apply_inputs).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.ir import Step

# GitHub's rule (mirrors executor/env.py `_INPUT_UNSAFE`, which tier 2 may
# not import): `with: {node-version: 20}` -> `INPUT_NODE_VERSION=20`.
_INPUT_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

_REMOTE_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)@(?P<ref>\S+)$")
"""`actions/checkout@v4` — exactly two path segments, then a ref. The ref may
contain anything (a branch with slashes is fine); the owner/repo parts are
loose but slug-ish so a URL or a bare word can't sneak through as remote."""

REMOTE_CACHE_ROOT = Path.home() / ".yeet" / "actions"
_GITHUB_CLONE_URL = "https://github.com/{owner}/{repo}.git"

GitClone = Callable[[str, str, Path], bool]  # (url, ref, dest)


@dataclass(frozen=True, slots=True)
class InputSpec:
    name: str
    description: str | None = None
    required: bool = False
    default: Any = None


@dataclass(slots=True)
class ResolvedAction:
    kind: str  # "composite" | "docker" | "node"
    action_dir: Path
    inputs: dict[str, InputSpec] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)  # composite only
    image: str | None = None  # docker: "Dockerfile" (built) or "docker://uri"
    main: str | None = None  # node: dist/index.js
    entrypoint: str | None = None  # docker: overrides CMD

    @property
    def display_name(self) -> str:
        return f"{self.kind} action in {self.action_dir}"


def resolve(uses: str, root: Path, bag: DiagnosticBag) -> ResolvedAction | None:
    """Turn a `uses:` string into a ResolvedAction, or None if not local.

    `None` is NOT an error: `owner/repo@ref` (remote, A20) and `docker://...`
    (executor's images module) are other people's business. Only a path that
    claims to be local but can't be satisfied is E313.
    """
    local = _local_path(uses, root)
    if local is None:
        return None

    action_yml = _find_action_yml(local, bag)
    if action_yml is None:
        return None

    data = _load_action_yml(action_yml, bag)
    if data is None:
        return None

    runs = data.get("runs")
    if not isinstance(runs, dict):
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message=f"`{uses}` isn't a valid action: action.yml has no `runs:` block",
                file=action_yml,
                pos=Position.unknown(),
                help="an action.yml needs `runs.using:` so yeet knows how to run it",
            )
        )
        return None

    using = runs.get("using")
    if not isinstance(using, str):
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message=f"`{uses}` isn't a valid action: `runs.using:` is missing",
                file=action_yml,
                pos=Position.unknown(),
            )
        )
        return None

    inputs = _parse_inputs(data.get("inputs"))
    kind = _kind_for(using)
    action = ResolvedAction(
        kind=kind,
        action_dir=local,
        inputs=inputs,
        image=_str_or_none(runs.get("image")),
        main=_str_or_none(runs.get("main")),
        entrypoint=_str_or_none(runs.get("entrypoint")),
    )

    if kind == "composite":
        steps = runs.get("steps")
        if not isinstance(steps, list) or not steps:
            bag.add(
                Diagnostic(
                    code="YEET-E313",
                    severity=Severity.ERROR,
                    message=f"`{uses}` is a composite action but `runs.steps:` is missing or empty",
                    file=action_yml,
                    pos=_pos_of_value(runs, "steps")
                    if isinstance(runs, dict)
                    else Position.unknown(),
                    help="a composite action runs its `runs.steps:` inline",
                )
            )
            return None
        action.steps = [_build_step(s, action_yml) for s in steps if isinstance(s, dict)]

    return action


def resolve_remote(
    uses: str,
    bag: DiagnosticBag,
    *,
    cache_root: Path | None = None,
    git_clone: GitClone | None = None,
) -> ResolvedAction | None:
    """`owner/repo@ref` -> shallow-clone into the cache, then resolve locally.

    Cached by ref: `~/.yeet/actions/<owner>/<repo>/<ref>/`. Once a ref is
    cached it is never re-fetched — refs are immutable (tags and SHAs), and a
    moving `@main` caching forever is the W402 lint's whole complaint.

    Returns None when the uses isn't the `owner/repo@ref` shape (not an error:
    docker:// and bare words are someone else's concern). A ref that FAILS to
    clone is E313 — the uses can't be satisfied, full stop.
    """
    parsed = _parse_remote(uses)
    if parsed is None:
        return None
    owner, repo, ref = parsed

    dest = (cache_root or REMOTE_CACHE_ROOT) / owner / repo / ref
    if not dest.is_dir():
        clone = git_clone or _git_clone
        ok = clone(_GITHUB_CLONE_URL.format(owner=owner, repo=repo), ref, dest)
        if not ok:
            bag.add(
                Diagnostic(
                    code="YEET-E313",
                    severity=Severity.ERROR,
                    message=f"could not clone `{uses}` into the action cache",
                    file=dest,
                    pos=Position.unknown(),
                    help="check the repo and ref spellings, and that you're online",
                )
            )
            return None

    return resolve(str(dest), dest, bag)


def _parse_remote(uses: str) -> tuple[str, str, str] | None:
    """`actions/checkout@v4` -> ("actions", "checkout", "v4"), else None.

    `uses` values that reach this are local paths (handled), docker:// URIs
    (not ours), or refs. A value with no `@` has no ref to pin and is not a
    remote ref — None.
    """
    match = _REMOTE_RE.match(uses.strip())
    if not match:
        return None
    return match.group("owner"), match.group("repo"), match.group("ref")


def _git_clone(url: str, ref: str, dest: Path) -> bool:
    """Shallow clone, ref-checkout. Never raises; report failure as E313."""
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, url, str(dest)],
            capture_output=True,
            timeout=120,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def apply_inputs(
    action: ResolvedAction,
    with_values: dict[str, Any],
    bag: DiagnosticBag,
    *,
    file: Path | None = None,
    pos: Position | None = None,
) -> dict[str, str]:
    """Merge `with:` + action defaults into `INPUT_*` env. E314 / W319.

    Only declared inputs become env vars; defaults come from action.yml.
    A `with:` key the action doesn't declare is W319, not an error — GitHub
    passes it through silently, but an action that ignores its inputs is
    usually a typo. Missing a `required: true` input is E314: the action will
    fail anyway, so fail before the container starts.
    """
    out: dict[str, str] = {}
    for name, spec in action.inputs.items():
        value = with_values.get(name, spec.default)
        if value is None:
            if spec.required:
                bag.add(
                    Diagnostic(
                        code="YEET-E314",
                        severity=Severity.ERROR,
                        message=f"required input `{name}` of this action isn't supplied",
                        file=file,
                        pos=pos,
                        help=(
                            f"add `with: {{ {name}: ... }}` to the step, "
                            "or give the input a default"
                        ),
                    )
                )
                continue
            value = ""
        out[input_env_name(name)] = str(value)

    declared = set(action.inputs)
    for key in with_values:
        if key not in declared:
            bag.add(
                Diagnostic(
                    code="YEET-W319",
                    severity=Severity.WARNING,
                    message=f"`with:` supplies `{key}` but the action doesn't declare it",
                    file=file,
                    pos=pos,
                    help=(
                        "check the spelling against the action's `inputs:` — "
                        "the input is silently ignored"
                    ),
                )
            )
    return out


def input_env_name(raw: str) -> str:
    """`node-version` -> `INPUT_NODE_VERSION`, per GitHub's convention."""
    name = _INPUT_UNSAFE.sub("_", str(raw)).strip("_").upper()
    return f"INPUT_{name}"


def composite_steps(action: ResolvedAction, input_env: dict[str, str]) -> list[Step]:
    """The inlined steps of a composite action, with the input env merged in.

    Pure: returns copies, never mutates the resolved action. The step's own
    explicit `env:` wins over `INPUT_*`, matching GitHub's precedence.
    """
    out: list[Step] = []
    for step in action.steps:
        merged = {**input_env, **(step.env or {})}
        out.append(
            Step(
                pos=step.pos,
                name=step.name,
                id=step.id,
                run=step.run,
                uses=step.uses,
                with_=dict(step.with_),
                env=merged,
                if_=step.if_,
                shell=step.shell,
                working_directory=step.working_directory,
                continue_on_error=step.continue_on_error,
                timeout_minutes=step.timeout_minutes,
                key_pos=dict(step.key_pos),
            )
        )
    return out


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _local_path(uses: str, root: Path) -> Path | None:
    """A uses string that names a directory we can look at. Else None."""
    p = Path(uses)
    if p.is_absolute():
        return p
    if uses.startswith((".", "~")):
        return (Path.home() / uses[1:]) if uses.startswith("~") else (root / uses)
    return None


def _find_action_yml(path: Path, bag: DiagnosticBag) -> Path | None:
    expanded = path.expanduser()
    if not expanded.is_dir():
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message=f"`{path}` doesn't point at a directory",
                file=expanded,
                pos=Position.unknown(),
                help=(
                    "local actions live under a directory (e.g. "
                    "./.yeet/actions/checkout) with an action.yml in it"
                ),
            )
        )
        return None
    for name in ("action.yml", "action.yaml"):
        candidate = expanded / name
        if candidate.is_file():
            return candidate
    bag.add(
        Diagnostic(
            code="YEET-E313",
            severity=Severity.ERROR,
            message=f"`{path}` has no action.yml",
            file=expanded,
            pos=Position.unknown(),
            help="an action directory needs an action.yml (or action.yaml)",
        )
    )
    return None


def _load_action_yml(path: Path, bag: DiagnosticBag) -> Any | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message=f"cannot read action.yml ({exc.strerror or exc})",
                file=path,
                pos=Position.unknown(),
            )
        )
        return None
    yaml = YAML(typ="rt")
    try:
        data = yaml.load(text)
    except MarkedYAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message=f"action.yml is not valid YAML: {exc.problem or 'syntax error'}",
                file=path,
                pos=Position(mark.line, mark.column) if mark else Position.unknown(),
            )
        )
        return None
    if not isinstance(data, dict):
        bag.add(
            Diagnostic(
                code="YEET-E313",
                severity=Severity.ERROR,
                message="action.yml's top level must be a mapping",
                file=path,
                pos=Position.unknown(),
            )
        )
        return None
    return data


def _parse_inputs(raw: Any) -> dict[str, InputSpec]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, InputSpec] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            out[str(name)] = InputSpec(name=str(name))
            continue
        out[str(name)] = InputSpec(
            name=str(name),
            description=_str_or_none(spec.get("description")),
            required=bool(spec.get("required", False)),
            default=spec.get("default"),
        )
    return out


def _kind_for(using: str) -> str:
    using_l = using.lower()
    if using_l == "composite":
        return "composite"
    if using_l.startswith("node"):
        return "node"
    if using_l == "docker":
        return "docker"
    return "docker" if "docker" in using_l else "composite"


def _build_step(data: Any, source: Path) -> Step:
    keys = [
        "name",
        "id",
        "run",
        "uses",
        "with",
        "env",
        "if",
        "shell",
        "working-directory",
        "continue-on-error",
        "timeout-minutes",
    ]
    anchor = next((k for k in keys if k in data), None)
    return Step(
        pos=_pos_of_value(data, anchor) if anchor else Position.unknown(),
        name=_str_or_none(data.get("name")),
        id=_str_or_none(data.get("id")),
        run=_str_or_none(data.get("run")),
        uses=_str_or_none(data.get("uses")),
        with_=dict(data.get("with")) if isinstance(data.get("with"), dict) else {},
        env=_as_str_dict(data.get("env")),
        if_=_str_or_none(data.get("if")),
        shell=_str_or_none(data.get("shell")),
        working_directory=_str_or_none(data.get("working-directory")),
        continue_on_error=bool(data.get("continue-on-error", False)),
        timeout_minutes=_int_or_none(data.get("timeout-minutes")),
    )


def _pos_of_value(mapping: Any, key: str) -> Position:
    lc = getattr(mapping, "lc", None)
    if lc is None:
        return Position.unknown()
    try:
        line, col = lc.value(key)
        return Position(line, col)
    except (KeyError, TypeError, ValueError):
        return Position.unknown()


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None and not isinstance(value, bool) else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
