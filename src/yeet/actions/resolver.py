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

import hashlib
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from yeet.core.config import cache_dir
from yeet.core.diagnostics import Diagnostic, DiagnosticBag, Position, Severity
from yeet.core.ir import Step
from yeet.core.refs import is_moving

# GitHub's rule (mirrors executor/env.py `_INPUT_UNSAFE`, which tier 2 may
# not import): `with: {node-version: 20}` -> `INPUT_NODE_VERSION=20`.
_INPUT_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

_REMOTE_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)@(?P<ref>\S+)$")
"""`actions/checkout@v4` — exactly two path segments, then a ref. The ref may
contain anything (a branch with slashes is fine); the owner/repo parts are
loose but slug-ish so a URL or a bare word can't sneak through as remote."""

REMOTE_CACHE_ROOT = cache_dir() / "actions"
"""`platformdirs`, not `~/.yeet/actions`. Two reasons: `cache_dir()` is already
the shallow, per-platform location this project uses for the tarball cache — and
its docstring is where the Windows path-length warning lives — and a project of
the user's own has a `.yeet/actions/` for LOCAL actions, so the old spelling put
two unrelated things one character apart."""

_GITHUB_CLONE_URL = "https://github.com/{owner}/{repo}.git"

DEFAULT_TTL_S = 24 * 60 * 60
"""How long a MOVING ref may be served from cache before it is fetched again.

A SHA or an exact tag is never re-fetched — it cannot have changed. `@v4` and
`@main` can, and do: a cache that held them forever would quietly pin a
workflow to whatever happened to land first, which is the opposite of what
someone writing `@main` asked for. `YEET_ACTION_TTL` (seconds, 0 disables the
re-fetch) is the override."""

_REF_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

GitClone = Callable[[str, str, Path], bool]  # (url, ref, dest)


class Offline(Exception):
    """The cache missed and the network is not allowed. Carries no message of
    its own: the caller has the `uses:` string and the cache path, which is
    what the user needs to see."""


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
    offline: bool = False,
    on_fetch: Callable[[str], None] | None = None,
) -> ResolvedAction | None:
    """`owner/repo@ref` -> fetch into the cache, then resolve it locally.

    Cached at `<cache_dir>/actions/<owner>/<repo>/<ref-slug>/`, and the cache is
    the whole design here. A `uses:` line reaching the network in the middle of
    a run is a real cost — it is slow, it fails on a plane, and it makes a run
    depend on github.com being up — so it happens once per ref and is announced
    every time through `on_fetch`. Silence would be the wrong default for
    something that leaves the machine.

    HOW LONG A CACHE ENTRY LIVES depends on what the ref is, because that is
    what decides whether it CAN be wrong. A SHA or an exact tag is immutable
    and is never fetched twice. `@v4` and `@main` are re-pointed by their
    authors — that is W402's entire complaint — so they are refreshed after
    `DEFAULT_TTL_S`. Serving a months-old `@main` forever would silently pin a
    workflow to whatever landed first, which is not what `@main` asked for.

    `offline=True` never touches the network: a hit is served as usual and a
    miss raises `Offline` for the caller to report against the workflow line.

    Returns None when the uses isn't the `owner/repo@ref` shape (not an error:
    docker:// and bare words are someone else's concern). A ref that FAILS to
    fetch is E313 — the uses can't be satisfied, full stop.
    """
    parsed = _parse_remote(uses)
    if parsed is None:
        return None
    owner, repo, ref = parsed

    dest = (cache_root or REMOTE_CACHE_ROOT) / owner / repo / _ref_slug(ref)
    if _needs_fetch(dest, ref):
        if offline:
            raise Offline(str(dest))
        if on_fetch is not None:
            on_fetch(uses)
        # Replaced, not fetched into: a half-written entry from an interrupted
        # run would otherwise be indistinguishable from a complete one, and
        # every later run would resolve against the wreckage.
        shutil.rmtree(dest, ignore_errors=True)
        clone = git_clone or _git_clone
        ok = clone(_GITHUB_CLONE_URL.format(owner=owner, repo=repo), ref, dest)
        if not ok:
            shutil.rmtree(dest, ignore_errors=True)
            bag.add(
                Diagnostic(
                    code="YEET-E313",
                    severity=Severity.ERROR,
                    message=f"could not fetch `{uses}` into the action cache",
                    file=dest,
                    pos=Position.unknown(),
                    help="check the repo and ref spellings, and that you're online",
                )
            )
            return None

    return resolve(str(dest), dest, bag)


def prune_actions(cache_root: Path | None = None) -> int:
    """Empty the fetched-action cache. Returns how many entries went.

    Counts `<owner>/<repo>/<ref>` directories rather than files, because that
    is the unit a user thinks in — one number per `uses:` line they will have
    to fetch again.
    """
    root = cache_root or REMOTE_CACHE_ROOT
    if not root.is_dir():
        return 0
    count = sum(1 for owner in root.iterdir() if owner.is_dir() for _ in _refs_under(owner))
    shutil.rmtree(root, ignore_errors=True)
    return count


def _refs_under(owner: Path) -> list[Path]:
    return [ref for repo in owner.iterdir() if repo.is_dir() for ref in repo.iterdir()]


def _needs_fetch(dest: Path, ref: str) -> bool:
    """Is the cached copy missing, or old enough that it might be wrong?"""
    if not dest.is_dir():
        return True
    if not is_moving(ref):
        return False
    ttl = _ttl_s()
    if ttl <= 0:
        return False
    try:
        age = time.time() - dest.stat().st_mtime
    except OSError:
        return True
    return age > ttl


def _ttl_s() -> int:
    """`YEET_ACTION_TTL` in seconds. Junk is not an error — it is the default.

    A typo'd environment variable must not stop a run: the failure mode of
    guessing wrong here is one extra fetch, and the failure mode of raising is
    a workflow that cannot run at all.
    """
    raw = os.environ.get("YEET_ACTION_TTL", "")
    if not raw.strip():
        return DEFAULT_TTL_S
    try:
        return int(raw.strip())
    except ValueError:
        return DEFAULT_TTL_S


def _ref_slug(ref: str) -> str:
    """A ref as ONE path segment, uniquely.

    `feature/x` is a legal branch and `<owner>/<repo>/feature/x` would nest it
    a level deeper than the cache expects — which also means a branch named
    `feature` and a branch named `feature/x` fight over the same name, one as a
    file and one as a directory. Flattening alone would collide `a/b` with
    `a-b`, so the readable part is kept for whoever goes looking in the cache
    and a hash of the REAL ref makes it unambiguous.
    """
    flat = _REF_UNSAFE.sub("-", ref).strip("-.")[:40] or "ref"
    return f"{flat}-{hashlib.sha256(ref.encode('utf-8')).hexdigest()[:8]}"


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
    """Put `url` at `ref` in `dest`. Never raises; failure is reported as E313.

    Through `actions/fetch.py` rather than `git clone --depth 1 --branch <ref>`,
    which is what this was and which COULD NOT CHECK OUT A SHA: `--branch` takes
    a branch or a tag, so pinning an action the way W402 tells you to —
    `uses: foo/bar@<40 hex>` — failed every single time. `fetch()` is init +
    fetch + checkout, the sequence that treats a branch, a tag and a SHA
    identically, and it brings the rest of what this needed anyway: no terminal
    prompt on a private repo, and a Docker fallback for a machine without git.
    """
    from yeet.actions import fetch as fetch_mod

    dest.parent.mkdir(parents=True, exist_ok=True)
    result = fetch_mod.fetch(mount=dest.parent, dest_rel=dest.name, source=url, ref=ref)
    return result.ok


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


def _inputs_context(action: ResolvedAction, with_values: dict[str, Any]) -> dict[str, str]:
    """`${{ inputs.<name> }}` for the action's own steps: `with:` over defaults.

    Keyed by the input's REAL name (`node-version`), not the env spelling
    (`INPUT_NODE_VERSION`) — an expression names the input as the action.yml
    declares it, and the mangling that makes a legal shell variable is a
    one-way trip.
    """
    out: dict[str, str] = {}
    for name, spec in action.inputs.items():
        value = with_values.get(name, spec.default)
        out[name] = "" if value is None else str(value)
    return out


def _rebase_uses(uses: str | None, action_dir: Path) -> str | None:
    """A composite's inner `uses: ./x` means "relative to the ACTION".

    Once the steps are inlined they are indistinguishable from the job's own,
    and the job resolves `./x` against the WORKSPACE. For an action cloned into
    the cache that is a different repository entirely, so the path is made
    absolute here, while the action it came from is still known.

    Only `./` and `../`. A `~`-relative path is the user's home in both frames,
    and `owner/repo@ref` and `docker://` mean the same thing wherever they are
    written — rewriting either would be inventing a path nobody asked for.
    """
    if uses is None or not uses.startswith(("./", "../")):
        return uses
    return str((action_dir / uses).resolve())


def composite_steps(
    action: ResolvedAction,
    input_env: dict[str, str],
    with_values: dict[str, Any] | None = None,
) -> list[Step]:
    """The inlined steps of a composite action, with its inputs bound to them.

    Pure: returns copies, never mutates the resolved action. The step's own
    explicit `env:` wins over `INPUT_*`, matching GitHub's precedence.

    Inputs are bound TWICE on purpose, because a workflow reaches them two
    ways and both have to work: `$INPUT_PATH` in a shell, which the env gives,
    and `${{ inputs.path }}` in an expression, which it does not — that form
    resolved to an empty string for as long as composite actions have run here.
    """
    resolved_inputs = _inputs_context(action, with_values or {})
    out: list[Step] = []
    for step in action.steps:
        merged = {**input_env, **(step.env or {})}
        out.append(
            Step(
                pos=step.pos,
                name=step.name,
                id=step.id,
                run=step.run,
                uses=_rebase_uses(step.uses, action.action_dir),
                with_=dict(step.with_),
                env=merged,
                if_=step.if_,
                shell=step.shell,
                working_directory=step.working_directory,
                continue_on_error=step.continue_on_error,
                timeout_minutes=step.timeout_minutes,
                action_inputs=resolved_inputs,
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
