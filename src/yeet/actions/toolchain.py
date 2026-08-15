"""`actions/setup-node` and friends: check the toolchain, never pretend to install one.

Owner: Dev D
Tier: 2 — may import from: core, expressions, reporting
See docs/architecture.md

WHY THIS FILE EXISTS. `setup-node`, `setup-python`, `setup-go` and `setup-java`
are the first step of an enormous share of real workflows, and every one of
them was SKIPPED with "could not be resolved to a local action". A skipped step
is green. So a workflow that says `node-version: 20` ran against whatever node
the image happened to have — 18, or none — went green, and the log said the
setup step was skipped in a line no one reads twice. That is the worst failure
mode a runner has: the wrong answer, confidently.

WHAT WE CAN HONESTLY DO. Not installation. These actions download a toolchain
tarball and unpack it into a hosted runner's tool cache; the equivalent here
would be mutating the user's machine or rebuilding the job's image mid-run, and
neither is something a `uses:` line should be allowed to do behind your back.

What we CAN do is check. The container (or the host, for `cooked_on: local`)
already provides some version of the toolchain, and the workflow already told
us which one it needs. Comparing those two is the entire value of the action
for a local run:

* right version   -> one line saying which, and where it came from
* wrong version   -> the step FAILS, naming both versions and how to fix it
* not installed   -> the step FAILS, saying yeet does not install toolchains
* unparseable request (`lts/*`, `>=18`) -> report, do not pretend to check

It is a probe SCRIPT rather than a built-in because a built-in runs in-process
on the host, and the question is about the CONTAINER. `node --version` on the
host of a Docker run is an answer to a different question. Inlining a step is
the only way the check happens where the job actually runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SETUP_NODE = "actions/setup-node"
SETUP_PYTHON = "actions/setup-python"
SETUP_GO = "actions/setup-go"
SETUP_JAVA = "actions/setup-java"


@dataclass(frozen=True, slots=True)
class Toolchain:
    name: str
    """`node`, `python`, ... — what the log calls it."""
    version_input: str
    """The `with:` key carrying the wanted version."""
    output: str
    """The step output GitHub's action sets, e.g. `node-version`."""
    probe: str
    """Shell that prints the raw version banner. Must work under `sh -e`."""
    binaries: str
    """Space-separated candidates, first one found wins. Reported when absent."""


#: `java -version` writes to STDERR (it has since 1.0 and it is not changing),
#: so every probe is written `2>&1` — one spelling, no per-tool exception.
TOOLCHAINS: dict[str, Toolchain] = {
    SETUP_NODE: Toolchain(
        name="node",
        version_input="node-version",
        output="node-version",
        probe="node --version 2>&1",
        binaries="node",
    ),
    SETUP_PYTHON: Toolchain(
        name="python",
        version_input="python-version",
        output="python-version",
        probe="{bin} --version 2>&1",
        binaries="python3 python",
    ),
    SETUP_GO: Toolchain(
        name="go",
        version_input="go-version",
        output="go-version",
        probe="go version 2>&1",
        binaries="go",
    ),
    SETUP_JAVA: Toolchain(
        name="java",
        version_input="java-version",
        output="java-version",
        probe="java -version 2>&1",
        binaries="java",
    ),
}

#: `20`, `20.x`, `v20`, `3.12`, `1.21.5`. Anything else — `>=18`, `lts/*`,
#: `latest`, `temurin` — is a range or an alias, and resolving those means
#: implementing npm's semver grammar plus each vendor's channel names. We
#: check what we can parse and say so plainly when we cannot.
_CONCRETE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:\.[xX*])?$")


def is_toolchain(name: str) -> bool:
    return name in TOOLCHAINS


def wanted_version(inputs: dict[str, Any]) -> str:
    """The version a `with:` block asks for, whichever key it used."""
    for key in ("node-version", "python-version", "go-version", "java-version", "version"):
        value = inputs.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize(version: str) -> str:
    """`v20` / `20.x` -> `20`; a range or alias -> "" (we cannot check it)."""
    match = _CONCRETE.match(version.strip())
    return match.group(1) if match else ""


def probe_script(uses: str, inputs: dict[str, Any]) -> str:
    """The shell a `setup-*` step becomes. POSIX sh, safe under `set -e`.

    The wanted version reaches the script through a variable assignment rather
    than being spliced into a command, because `with: {node-version: "; rm -rf
    ~"}` is a workflow file that would otherwise run as a shell.
    """
    tool = TOOLCHAINS[uses]
    raw = wanted_version(inputs)
    want = normalize(raw)

    probe = tool.probe if "{bin}" not in tool.probe else tool.probe.replace("{bin}", '"$found"')
    return _TEMPLATE.format(
        label=uses,
        tool=tool.name,
        binaries=tool.binaries,
        output=tool.output,
        probe=probe,
        raw=_sh_quote(raw),
        want=_sh_quote(want),
    )


def _sh_quote(value: str) -> str:
    """Single-quote for sh, closing and reopening around embedded quotes."""
    return "'" + value.replace("'", "'\\''") + "'"


#: `set -e` is already applied by `shell_argv` for bash, but this script is
#: written so it does not depend on that: every failure path exits explicitly.
#: A probe that dies on `command -v` under `-e` would produce no message at all,
#: which is the exact behaviour this whole module exists to remove.
_TEMPLATE = r"""
tool="{tool}"
want={want}
raw={raw}

found=""
for candidate in {binaries}; do
  if command -v "$candidate" >/dev/null 2>&1; then
    found="$candidate"
    break
  fi
done

if [ -z "$found" ]; then
  echo "$tool is not installed in this environment." >&2
  if [ -n "$raw" ]; then
    echo "This workflow asks for $tool $raw, and yeet does not install toolchains:" >&2
    echo "  a 'uses: {label}' cannot add software to a running container." >&2
  fi
  echo "Fix it by choosing an image that has $tool - 'cooked_on:' in the job, or" >&2
  echo "a Dockerfile - or by installing $tool if this job is 'cooked_on: local'." >&2
  exit 1
fi

banner=$({probe} || true)
# The version is the first dotted number in the banner, whatever the tool wraps
# it in: 'v20.11.1', 'Python 3.12.4', 'go version go1.21.5 linux/arm64',
# 'openjdk version "17.0.9"'. One extractor, because four regexes is four
# things to get wrong the next time a vendor reformats their banner.
# `|| true` is load-bearing: the shell runs with `-o pipefail`, grep exits 1
# when the banner holds no version, and head closing the pipe early can kill
# grep with SIGPIPE. Either one aborts the script before the empty-check below
# and the user gets a step that failed with no output at all.
have=$(printf '%s' "$banner" | tr -c '0-9.\n' ' ' | tr ' ' '\n' \
  | grep -E '^[0-9]+(\.[0-9]+)*$' | head -n 1 || true)

if [ -z "$have" ]; then
  # A `$tool` on PATH that cannot say what version it is usually is not one:
  # macOS ships a /usr/bin/java stub for exactly this, and it answers every
  # invocation with an advert for java.com. Print what it did say - that IS
  # the diagnosis - rather than a version-parsing complaint of our own.
  echo "$tool is on PATH but did not report a version yeet could read:" >&2
  printf '  %s\n' "$banner" >&2
  exit 1
fi

# Java 8 and earlier report '1.8.0_392'. The number everyone MEANS is the one
# after the 1., and a workflow asking for java-version 8 is asking for that.
case "$tool.$have" in
  java.1.*) have=$(printf '%s' "$have" | cut -d. -f2-) ;;
esac

# WHICH one, not just which version: a container with three pythons on PATH is
# ordinary, and "python 3.11.2" alone does not tell you the job picked the one
# you meant.
echo "$tool $have at $(command -v "$found") - provided by the environment, not installed by yeet"
if [ -n "$GITHUB_OUTPUT" ]; then
  echo "{output}=$have" >> "$GITHUB_OUTPUT"
fi

if [ -z "$raw" ]; then
  exit 0
fi

if [ -z "$want" ]; then
  echo "requested $tool $raw - a range or alias yeet cannot resolve, so the" >&2
  echo "installed $have was NOT checked against it." >&2
  exit 0
fi

# Prefix match on whole dot-separated components: want 20 matches 20.11.1 but
# not 2.0.1, and want 3.12 matches 3.12.4 but not 3.1. Comparing the strings
# with a plain prefix test is what makes '2' match '20'.
case "$have." in
  "$want".*)
    echo "$tool $have satisfies $raw"
    ;;
  *)
    echo "$tool $have does NOT satisfy the requested $raw." >&2
    echo "yeet cannot install toolchains: 'uses: {label}' has no way to add" >&2
    echo "software to a container that is already running. Point the job at an" >&2
    echo "image that carries $tool $raw ('cooked_on:' or a Dockerfile)." >&2
    exit 1
    ;;
esac
"""
