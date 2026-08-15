"""`upload-artifact`, `download-artifact` and `cache`, done locally.

Owner: Dev D
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md

It lives in `storage/` and not in `executor/` because of the tier contract:
the two are siblings and may not import each other (docs/adr/0007). The types
it speaks are `core.builtins`, at tier 0 where both sides can see them, and
`cli/cmd_run` passes `run_builtin` down into the step loop. The executor
invokes a callable and never learns that `.yeet/artifacts/` exists.

On GitHub these three are node actions that talk to a hosted service. There is
no service here, so running their JavaScript would fail at the first HTTP call
even once C16 lands. What a local runner owes the user is their OBSERVABLE
behaviour: files survive from one job to the next, a cache key hits or misses,
and `steps.<id>.outputs.cache-hit` is the string a workflow can branch on.

These run IN PROCESS, on the host, against the workspace — not inside the job's
container. That is a deliberate limit and it is the honest one: the workspace
is a bind mount, so the host sees exactly the bytes the container just wrote.

`cache` registers a POST action. GitHub saves a cache when the job ENDS, not
when the `uses:` line is reached — saving at the step itself would tar the
dependency directory before the install step had populated it, which is the
one mistake that makes a cache silently useless forever.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yeet.core.builtins import BuiltinContext, BuiltinResult
from yeet.storage import artifacts as artifacts_mod
from yeet.storage import cache as cache_mod

CACHE_HIT = "cache-hit"


def run_builtin(name: str, ctx: BuiltinContext) -> BuiltinResult:
    handler = _HANDLERS.get(name)
    if handler is None:  # pragma: no cover - plan_uses gates this
        return BuiltinResult(ok=False, message=f"no built-in named {name}")
    return handler(ctx)


def _upload_artifact(ctx: BuiltinContext) -> BuiltinResult:
    name = _text(ctx.inputs.get("name")) or "artifact"
    patterns = _lines(ctx.inputs.get("path"))
    if not patterns:
        return BuiltinResult(ok=False, message="upload-artifact needs a `path:`")

    count = artifacts_mod.store_artifact(ctx.root, ctx.run_id, name, patterns, base=ctx.workspace)
    if count == 0:
        # GitHub warns rather than fails here, and so do we: a pattern that
        # matches nothing is usually a typo, but failing the job over it would
        # break workflows that upload optional output.
        ctx.emit(f"no files matched {patterns} — artifact `{name}` is empty")
        return BuiltinResult(ok=True, message="no files matched")

    ctx.emit(f"uploaded {count} file(s) as artifact `{name}`")
    return BuiltinResult(ok=True)


def _download_artifact(ctx: BuiltinContext) -> BuiltinResult:
    name = _text(ctx.inputs.get("name")) or "artifact"
    target = ctx.workspace / _text(ctx.inputs.get("path")) if ctx.inputs.get("path") else None
    dest = target or ctx.workspace

    count = artifacts_mod.load_artifact(ctx.root, ctx.run_id, name, dest)
    if count == 0:
        ctx.emit(f"no artifact named `{name}` in this run")
        return BuiltinResult(ok=True, message="nothing to download")

    ctx.emit(f"downloaded {count} file(s) from artifact `{name}`")
    return BuiltinResult(ok=True)


def _cache(ctx: BuiltinContext) -> BuiltinResult:
    key = _text(ctx.inputs.get("key"))
    paths = [ctx.workspace / p for p in _lines(ctx.inputs.get("path"))]
    if not key or not paths:
        return BuiltinResult(ok=False, message="cache needs both `key:` and `path:`")

    restore_keys = _lines(ctx.inputs.get("restore-keys"))
    hit = cache_mod.restore_cache(key, restore_keys, dest=ctx.workspace)

    if hit is not None and hit.exact:
        ctx.emit(f"cache hit for `{key}`")
    elif hit is not None:
        ctx.emit(f"cache miss for `{key}` — restored from `{hit.key}`")
    else:
        ctx.emit(f"cache miss for `{key}`")

    # Save at job end, not now. See the module docstring.
    if hit is None or not hit.exact:
        ctx.post.append(lambda: _save(ctx, key, paths))

    # GitHub's `cache-hit` is 'true' only for an EXACT match. A restore-key hit
    # reports 'false', which is what makes `if: cache-hit != 'true'` around an
    # install step correct: the deps are warm but not necessarily complete.
    return BuiltinResult(ok=True, outputs={CACHE_HIT: "true" if hit and hit.exact else "false"})


def _save(ctx: BuiltinContext, key: str, paths: list[Path]) -> None:
    try:
        saved = cache_mod.save_cache(key, paths, base=ctx.workspace)
    except OSError as exc:
        ctx.emit(f"could not save cache `{key}`: {exc}")
        return
    if saved is None:
        ctx.emit(f"nothing to cache for `{key}` — none of its paths exist")
    else:
        ctx.emit(f"saved cache `{key}`")


def _checkout(ctx: BuiltinContext) -> BuiltinResult:
    """`actions/checkout` — a no-op by default, a real fetch when asked.

    THE DEFAULT. On GitHub the workspace starts empty and this clones into it.
    Locally the workspace IS the checkout: it is the directory yeet was pointed
    at, bind-mounted into the container. There is nothing to fetch and nothing
    that could be more current than what is already there. It is a built-in
    rather than a skip because it is the first step of nearly every real
    workflow, and a run whose opening line reads `skipped (not the vibe)` looks
    like something failed before anything started.

    WHEN A `repository:` OR `ref:` IS GIVEN. Those name something other than the
    working tree, and a workflow that checks out a second repo alongside the
    first is ordinary. We fetch it — through host git, or through a git
    container when the machine has Docker but no git (`actions/fetch.py`).

    THE ONE THING THIS REFUSES. Fetching over the workspace root. The user
    pointed us at a directory they are working in; replacing its contents with
    a different ref would discard uncommitted work to satisfy a line in a YAML
    file, and no amount of logging makes that acceptable. `path:` is how
    `actions/checkout` already spells "somewhere else", so a `ref:` without a
    `path:` is refused with the one-line fix rather than obeyed.
    """
    from yeet.actions import fetch as fetch_mod

    repository = _text(ctx.inputs.get("repository"))
    ref = _text(ctx.inputs.get("ref"))
    path = _text(ctx.inputs.get("path"))

    if not repository and not ref:
        if path:
            # Nothing to fetch, but say where the code the job will use lives.
            ctx.emit(f"the workspace is already this repository (ignoring `path: {path}`)")
        else:
            ctx.emit("the workspace is already this repository")
        return BuiltinResult(ok=True)

    if not path:
        return BuiltinResult(
            ok=False,
            message=(
                f"`checkout` asks for `{repository or ref}` but no `path:`. Checking it out "
                "over the workspace would discard your uncommitted work — add "
                "`path: <subdir>` to fetch it alongside instead."
            ),
        )

    source = _source_url(repository, ctx.workspace)
    ctx.emit(f"fetching {source}{f' at {ref}' if ref else ''} into {path}/")
    result = fetch_mod.fetch(mount=ctx.workspace, dest_rel=path, source=source, ref=ref)
    if not result.ok:
        return BuiltinResult(ok=False, message=result.message)

    where = f" via {result.via}" if result.via else ""
    at = f" at {result.commit[:12]}" if result.commit else ""
    ctx.emit(f"checked out into {path}/{at}{where}")
    return BuiltinResult(ok=True)


def _source_url(repository: str, workspace: Path) -> str:
    """`owner/repo` -> a GitHub URL; empty -> this workspace.

    A bare `ref:` with no `repository:` means "this repo, at that ref", and the
    local clone is the fastest and most private place to get it — no network,
    and it already has the objects.
    """
    if not repository:
        return str(workspace)
    if "://" in repository or repository.startswith("git@"):
        return repository
    return f"https://github.com/{repository}.git"


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _lines(value: object) -> list[str]:
    """`path:` is a multi-line string in every real workflow that uses it."""
    return [line.strip() for line in _text(value).splitlines() if line.strip()]


_HANDLERS: dict[str, Callable[[BuiltinContext], BuiltinResult]] = {
    "actions/upload-artifact": _upload_artifact,
    "actions/download-artifact": _download_artifact,
    "actions/cache": _cache,
    "actions/checkout": _checkout,
}
