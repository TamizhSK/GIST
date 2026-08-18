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

import shutil
from collections.abc import Callable
from fnmatch import fnmatch
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
    """`if-no-files-found` and `overwrite` are the two that decide pass/fail.

    Both used to be ignored, and ignoring them is the expensive kind of wrong:
    a workflow that set `if-no-files-found: error` because an empty artifact
    means its build produced nothing went GREEN here and red on GitHub, which
    is precisely the direction a local runner must never get wrong.
    """
    name = _text(ctx.inputs.get("name")) or "artifact"
    patterns = _lines(ctx.inputs.get("path"))
    if not patterns:
        return BuiltinResult(ok=False, message="upload-artifact needs a `path:`")

    # v4 refuses to write over an artifact that already exists in the run; v3
    # merged into it silently. The refusal is the behaviour people hit, because
    # it is what turns a matrix uploading one name into a red build.
    overwrite = _flag(ctx.inputs.get("overwrite"))
    existing = artifacts_mod.artifact_dir(ctx.root, ctx.run_id, name)
    if existing.is_dir() and not overwrite:
        return BuiltinResult(
            ok=False,
            message=(
                f"an artifact named `{name}` already exists in this run. Give this upload "
                "a different `name:` — a matrix leg usually wants "
                "`name: build-${{ matrix.os }}` — or set `overwrite: true`."
            ),
        )
    if existing.is_dir() and overwrite:
        shutil.rmtree(existing, ignore_errors=True)

    count = artifacts_mod.store_artifact(ctx.root, ctx.run_id, name, patterns, base=ctx.workspace)
    if count == 0:
        behaviour = _text(ctx.inputs.get("if-no-files-found")).lower() or "warn"
        if behaviour == "error":
            return BuiltinResult(
                ok=False,
                message=f"no files matched {patterns} and `if-no-files-found: error` is set",
            )
        if behaviour != "ignore":
            ctx.emit(f"no files matched {patterns} — artifact `{name}` is empty")
        return BuiltinResult(ok=True, message="no files matched", outputs=_upload_outputs(name))

    ctx.emit(f"uploaded {count} file(s) as artifact `{name}`")
    return BuiltinResult(ok=True, outputs=_upload_outputs(name))


def _upload_outputs(name: str) -> dict[str, str]:
    """`artifact-id` and `artifact-url` exist on GitHub and cannot here.

    There is no artifact service and no URL that would resolve, so the id is
    the name — stable and unique within a run, which is the only property a
    workflow can actually depend on — and the url is omitted rather than
    invented. A plausible-looking dead link is worse than a missing one.
    """
    return {"artifact-id": name}


def _download_artifact(ctx: BuiltinContext) -> BuiltinResult:
    """No `name:` means EVERY artifact of the run, which is v4's big change.

    Defaulting the name to `"artifact"` (what this did) quietly downloaded one
    specific artifact that usually did not exist, so the step said "nothing to
    download" and went green while the job that needed the files failed later
    for a reason that named neither this step nor the artifact.
    """
    name = _text(ctx.inputs.get("name"))
    pattern = _text(ctx.inputs.get("pattern"))
    merge = _flag(ctx.inputs.get("merge-multiple"))
    dest = (
        ctx.workspace / _text(ctx.inputs.get("path")) if ctx.inputs.get("path") else ctx.workspace
    )

    if name:
        wanted = [name]
    else:
        available = [d.name for d in artifacts_mod.list_artifacts(ctx.root, ctx.run_id)]
        wanted = [a for a in available if fnmatch(a, pattern)] if pattern else available

    if not wanted:
        ctx.emit(f"no artifact {'matching ' + pattern if pattern else ''} in this run".strip())
        return BuiltinResult(ok=True, message="nothing to download", outputs={})

    total = 0
    for artifact in wanted:
        # One `name:`, or `merge-multiple`, lands flat in `path:`. Several
        # artifacts otherwise each get a directory of their own — two builds
        # both uploading `dist/index.js` would silently overwrite each other.
        into = dest if (name or merge) else dest / artifact
        total += artifacts_mod.load_artifact(ctx.root, ctx.run_id, artifact, into)

    if total == 0 and name:
        ctx.emit(f"no artifact named `{name}` in this run")
        return BuiltinResult(
            ok=True, message="nothing to download", outputs=_download_outputs(dest)
        )

    ctx.emit(f"downloaded {total} file(s) from {len(wanted)} artifact(s)")
    return BuiltinResult(ok=True, outputs=_download_outputs(dest))


def _download_outputs(dest: Path) -> dict[str, str]:
    return {"download-path": str(dest)}


def _cache(ctx: BuiltinContext) -> BuiltinResult:
    """Restore now, save at job end. `fail-on-cache-miss` is the pass/fail one.

    A workflow that sets it has decided a miss is a broken build — a release
    job that must not silently recompile what an earlier job was supposed to
    have cached. Ignoring the input turned that assertion into a no-op.
    """
    key = _text(ctx.inputs.get("key"))
    paths = [ctx.workspace / p for p in _lines(ctx.inputs.get("path"))]
    if not key or not paths:
        return BuiltinResult(ok=False, message="cache needs both `key:` and `path:`")

    restore_keys = _lines(ctx.inputs.get("restore-keys"))
    lookup_only = _flag(ctx.inputs.get("lookup-only"))
    # `lookup-only` asks whether the entry EXISTS without unpacking it, which
    # is how a workflow decides to skip an expensive build. Restoring anyway
    # would be the difference between a warm workspace and a cold one.
    hit = cache_mod.restore_cache(key, restore_keys, dest=ctx.workspace, extract=not lookup_only)

    if hit is not None and hit.exact:
        ctx.emit(f"cache {'found' if lookup_only else 'hit'} for `{key}`")
    elif hit is not None:
        ctx.emit(f"cache miss for `{key}` — restored from `{hit.key}`")
    else:
        ctx.emit(f"cache miss for `{key}`")

    if hit is None and _flag(ctx.inputs.get("fail-on-cache-miss")):
        return BuiltinResult(
            ok=False,
            message=f"no cache entry for `{key}` and `fail-on-cache-miss: true` is set",
        )

    # Save at job end, not now. See the module docstring. `lookup-only` never
    # saves: it did not restore, so it has nothing to say about these paths.
    if not lookup_only and (hit is None or not hit.exact):
        ctx.post.append(lambda: _save(ctx, key, paths))

    # GitHub's `cache-hit` is 'true' only for an EXACT match. A restore-key hit
    # reports 'false', which is what makes `if: cache-hit != 'true'` around an
    # install step correct: the deps are warm but not necessarily complete.
    return BuiltinResult(
        ok=True,
        outputs={
            CACHE_HIT: "true" if hit and hit.exact else "false",
            # Which key was ASKED for and which one answered. A restore-key hit
            # reports `cache-hit: false`, so these two are the only way a
            # workflow can tell "nothing at all" from "something close".
            "cache-primary-key": key,
            "cache-matched-key": hit.key if hit else "",
        },
    )


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
    """`actions/checkout` — fills an empty workspace, respects a full one.

    WHICH OF THE TWO IT IS depends on the workspace it was handed. On GitHub
    the workspace always starts empty and this clones into it; locally there
    are two shapes, and the difference is `ctx.workspace != ctx.root`:

    * BIND-MOUNTED (the default) — the workspace IS the checkout: the directory
      yeet was pointed at, mounted into the container. There is nothing to
      fetch and nothing that could be more current than what is already there.
      It stays a built-in rather than a skip because it is the first step of
      nearly every real workflow, and a run whose opening line reads `skipped
      (not the vibe)` looks like something failed before anything started.

    * ISOLATED (`yeet run --clean`) — the workspace is this job's own empty
      directory and filling it is the entire job of this action, exactly as on
      GitHub. The source is the project root, which already has the objects, so
      the common case costs no network. Before this, `--clean` printed "the
      workspace is already this repository" over an empty directory and every
      step after it ran against nothing.

    WHEN A `repository:` OR `ref:` IS GIVEN. Those name something other than
    the working tree, and a workflow that checks out a second repo alongside
    the first is ordinary. We fetch it — through host git, or through a git
    container when the machine has Docker but no git (`actions/fetch.py`).

    THE ONE THING THIS REFUSES. Fetching over a BIND-MOUNTED workspace root.
    The user pointed us at a directory they are working in; replacing its
    contents with a different ref would discard uncommitted work to satisfy a
    line in a YAML file, and no amount of logging makes that acceptable.
    `path:` is how `actions/checkout` already spells "somewhere else", so a
    `ref:` without a `path:` is refused with the one-line fix rather than
    obeyed. An isolated workspace is ours and is not covered by this.

    INPUTS THAT DO NOTHING, and why they are still accepted silently:
    `clean:` asks for `git clean -ffdx` before the fetch, and neither shape can
    honour it — an isolated workspace is already empty and a bind-mounted one
    is refused. `persist-credentials`, `set-safe-directory` and `token` are
    about GitHub's credential handling; host git carries the user's own. A
    warning on every one of these would fire on most real workflow files.
    """
    from yeet.actions import fetch as fetch_mod

    repository = _text(ctx.inputs.get("repository"))
    ref = _text(ctx.inputs.get("ref"))
    path = _text(ctx.inputs.get("path"))
    depth = _fetch_depth(ctx.inputs.get("fetch-depth"))
    submodules = _submodules(ctx.inputs.get("submodules"))

    if not repository and not ref and not ctx.isolated:
        if path:
            # Nothing to fetch, but say where the code the job will use lives.
            ctx.emit(f"the workspace is already this repository (ignoring `path: {path}`)")
        else:
            ctx.emit("the workspace is already this repository")
        return BuiltinResult(ok=True, outputs=_checkout_outputs(ctx.workspace, ref))

    if not path and not ctx.isolated:
        return BuiltinResult(
            ok=False,
            message=(
                f"`checkout` asks for `{repository or ref}` but no `path:`. Checking it out "
                "over the workspace would discard your uncommitted work — add "
                "`path: <subdir>` to fetch it alongside instead."
            ),
        )

    # "This repository" is the project root when the workspace is the empty
    # directory we are about to fill, and the workspace itself otherwise — in
    # the ordinary run those are the same path.
    local_root = ctx.root if ctx.isolated else ctx.workspace
    source = _source_url(repository, local_root)
    # The second bind, and the only case that needs one: an isolated workspace
    # is fed from the project root, which is nowhere near it on the host.
    source_mount = local_root if (ctx.isolated and not repository) else None

    where_to = f"{path}/" if path else "the workspace"
    ctx.emit(f"fetching {source}{f' at {ref}' if ref else ''} into {where_to}")
    result = fetch_mod.fetch(
        mount=ctx.workspace,
        dest_rel=path,
        source=source,
        ref=ref,
        depth=depth,
        submodules=submodules,
        source_mount=source_mount,
    )
    if not result.ok:
        return BuiltinResult(ok=False, message=result.message)

    where = f" via {result.via}" if result.via else ""
    at = f" at {result.commit[:12]}" if result.commit else ""
    ctx.emit(f"checked out into {where_to}{at}{where}")
    return BuiltinResult(
        ok=True,
        outputs={"ref": ref or "HEAD", "commit": result.commit},
    )


def _checkout_outputs(root: Path, ref: str) -> dict[str, str]:
    """`steps.<id>.outputs.ref` / `.commit` for the no-op default path.

    A workflow reading `outputs.commit` must not get an empty string just
    because we had nothing to fetch — the commit is right there in the repo we
    are standing in. `rev_parse` answers "" when git cannot say, which is the
    same non-answer an empty output would have been, only honest about it.
    """
    from yeet.actions import fetch as fetch_mod

    return {"ref": ref or "HEAD", "commit": fetch_mod.rev_parse(root, "HEAD")}


def _fetch_depth(value: object) -> int:
    """`fetch-depth: 0` means FULL history to GitHub, and the default is 1.

    Workflows that run `git describe --tags`, `git log --oneline`, or any tool
    counting commits set `fetch-depth: 0` and are broken by a shallow tree in a
    way whose error message never mentions the checkout.
    """
    if value is None:
        return 1
    try:
        depth = int(str(value).strip())
    except (TypeError, ValueError):
        return 1
    return max(depth, 0)


def _submodules(value: object) -> str:
    """`true` -> one level, `recursive` -> all the way down, anything else off."""
    text = _text(value).lower()
    if text == "recursive":
        return "recursive"
    return "1" if text in ("true", "yes", "on") else ""


def _source_url(repository: str, root: Path) -> str:
    """`owner/repo` -> a GitHub URL; empty -> the project root.

    A bare `ref:` with no `repository:` means "this repo, at that ref", and the
    local clone is the fastest and most private place to get it — no network,
    and it already has the objects. The ROOT rather than the workspace: under
    `--clean` the workspace is the empty directory we are about to fill, and
    asking it to be its own source fetches nothing from nowhere.
    """
    if not repository:
        return str(root)
    if "://" in repository or repository.startswith("git@"):
        return repository
    return f"https://github.com/{repository}.git"


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _flag(value: object) -> bool:
    """A workflow boolean. `true`, `'true'` and `True` all arrive here.

    YAML gives a real bool for `overwrite: true`, and `${{ }}` interpolation
    gives the STRING "true" for the same thing written as an expression — which
    is truthy either way in Python, and so is "false".
    """
    return _text(value).lower() in ("true", "yes", "on", "1")


def _lines(value: object) -> list[str]:
    """`path:` is a multi-line string in every real workflow that uses it."""
    return [line.strip() for line in _text(value).splitlines() if line.strip()]


_HANDLERS: dict[str, Callable[[BuiltinContext], BuiltinResult]] = {
    "actions/upload-artifact": _upload_artifact,
    "actions/download-artifact": _download_artifact,
    "actions/cache": _cache,
    "actions/checkout": _checkout,
}
