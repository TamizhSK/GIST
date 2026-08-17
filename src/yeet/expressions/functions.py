"""The expression builtins: contains, startsWith, endsWith, format, join,
toJSON, fromJSON, hashFiles, and success/failure/always/cancelled.

Every function has the same signature — `(args, ctx) -> value` — so the
evaluator can hand it the already-evaluated argument list and the runtime
context, and the registry stays a plain dict. `ctx.root` feeds `hashFiles`;
`ctx.needs` feeds the status functions.

Owner: Dev B
Tier: 1 — may import from: core
See docs/architecture.md
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yeet.expressions._comparison import loose_equal
from yeet.expressions.contexts import Contexts

Function = Callable[[list[Any], Contexts], Any]

_NUMERIC_PLACEHOLDER = re.compile(r"\{(\d+)\}")


# --- pure value functions ----------------------------------------------------


def contains(args: list[Any], ctx: Contexts) -> Any:
    """GitHub's contains(search, item). Case-insensitive for strings.

    When `search` is an array, membership uses loose equality so
    `contains([1, 2], '2')` is true — consistent with every other comparison
    in the language.
    """
    if len(args) < 2:
        raise ValueError("contains(search, item) needs two arguments")
    search, item = args[0], args[1]
    if isinstance(search, str):
        return item is not None and item.casefold() in search.casefold()
    if isinstance(search, (list, tuple)):
        return any(loose_equal(element, item) for element in search)
    raise ValueError(f"contains() cannot search a {type(search).__name__}")


def starts_with(args: list[Any], ctx: Contexts) -> Any:
    if len(args) < 2:
        raise ValueError("startsWith(searchString, searchValue) needs two arguments")
    search, prefix = args[0], args[1]
    if not isinstance(search, str) or not isinstance(prefix, str):
        raise ValueError("startsWith() arguments must be strings")
    return search.casefold().startswith(prefix.casefold())


def ends_with(args: list[Any], ctx: Contexts) -> Any:
    if len(args) < 2:
        raise ValueError("endsWith(searchString, searchValue) needs two arguments")
    search, suffix = args[0], args[1]
    if not isinstance(search, str) or not isinstance(suffix, str):
        raise ValueError("endsWith() arguments must be strings")
    return search.casefold().endswith(suffix.casefold())


def format_value(args: list[Any], ctx: Contexts) -> Any:
    """`format('Hello {0} {1}', 'World', '!')`. Missing or null values render
    as empty strings; unknown placeholders are left alone (GitHub keeps
    literal `{3}` text when only `{0}`/`{1}` were supplied)."""
    if not args or not isinstance(args[0], str):
        raise ValueError("format(string, replaceValue0, ...) needs a string first")

    template = args[0]
    replacements = args[1:]

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index < len(replacements):
            return _stringify(replacements[index])
        return ""

    return _NUMERIC_PLACEHOLDER.sub(replace, template)


def join(args: list[Any], ctx: Contexts) -> Any:
    """`join(array, optionalSeparator)`. Default separator is `,`. Null or
    non-string elements join as empty strings, matching GitHub."""
    if not args or not isinstance(args[0], (list, tuple)):
        raise ValueError("join(array, optionalSeparator) needs an array first")
    separator = args[1] if len(args) > 1 and args[1] is not None else ","
    if not isinstance(separator, str):
        raise ValueError("join() separator must be a string")
    return separator.join(_stringify(element) for element in args[0])


def to_json(args: list[Any], ctx: Contexts) -> Any:
    if len(args) != 1:
        raise ValueError("toJSON(value) takes exactly one argument")
    return json.dumps(args[0], ensure_ascii=False, separators=(",", ":"), default=str)


def from_json(args: list[Any], ctx: Contexts) -> Any:
    if len(args) != 1 or not isinstance(args[0], str):
        raise ValueError("fromJSON(value) takes exactly one JSON string")
    try:
        return json.loads(args[0])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fromJSON() could not parse {args[0]!r}") from exc


def hash_files(args: list[Any], ctx: Contexts) -> Any:
    """`hashFiles(globPattern...)`. Deterministic across platforms because the
    matched paths are sorted before hashing — see docs/architecture.md §10.10.
    Returns the empty string when nothing matches, like GitHub."""
    if not args:
        raise ValueError("hashFiles(globPattern...) needs at least one pattern")
    patterns = [arg for arg in args if isinstance(arg, str)]
    if not patterns:
        raise ValueError("hashFiles() patterns must be strings")
    return hash_files_from(patterns, ctx.root)


def hash_files_from(patterns: list[str], root: Path) -> str:
    """Sorted, deduplicated, one SHA-256 over relative path + content + size.

    Keeping the byte size in the hash means a touched file (mtime change with
    identical content) still counts as unchanged — the thing caches want — while
    path + content catch real edits. `**` globs are rooted at `root`.
    """
    seen: dict[Path, None] = {}
    for pattern in patterns:
        for path in sorted(root.glob(pattern), key=lambda p: str(p.relative_to(root))):
            if path.is_file():
                seen[path] = None
    if not seen:
        return ""

    digest = hashlib.sha256()
    for path in sorted(seen, key=lambda p: str(p.relative_to(root))):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        content = path.read_bytes()
        digest.update(content)
        digest.update(b"\x00")
        digest.update(str(len(content)).encode("ascii"))
    return digest.hexdigest()


# --- status functions --------------------------------------------------------
#
# These answer "how did the run go so far", which only the runner knows. The
# runner hands it over as `ctx.needs`: job key -> result, where a result is
# either the plain dict shape below or a core.result.JobResult. Anything not
# yet finished counts as fine — an absent job must not look like a failure.


def _needs_ok(ctx: Contexts) -> bool:
    for value in ctx.needs.values():
        if isinstance(value, dict):
            result = value.get("result")
            if result is not None and result != "success":
                return False
            continue
        ok = getattr(getattr(value, "status", None), "ok", None)
        if ok is not None and not ok:
            return False
    return True


def success(args: list[Any], ctx: Contexts) -> Any:
    if args:
        raise ValueError("success() takes no arguments")
    return _needs_ok(ctx)


def failure(args: list[Any], ctx: Contexts) -> Any:
    if args:
        raise ValueError("failure() takes no arguments")
    return not _needs_ok(ctx)


def always(args: list[Any], ctx: Contexts) -> Any:
    if args:
        raise ValueError("always() takes no arguments")
    return True


def cancelled(args: list[Any], ctx: Contexts) -> Any:
    if args:
        raise ValueError("cancelled() takes no arguments")
    return False


# --- registry ----------------------------------------------------------------


FUNCTIONS: dict[str, Function] = {
    "contains": contains,
    "startswith": starts_with,
    "endswith": ends_with,
    "format": format_value,
    "join": join,
    "tojson": to_json,
    "fromjson": from_json,
    "hashfiles": hash_files,
    "success": success,
    "failure": failure,
    "always": always,
    "cancelled": cancelled,
}


def lookup(name: str) -> Function:
    """Case-insensitive. Unknown names resolve to a null-returning stub —
    E311 reports them at validation time; evaluation degrades instead of
    killing the run."""
    fn = FUNCTIONS.get(name.lower())
    if fn is not None:
        return fn
    return lambda args, ctx: None


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)
