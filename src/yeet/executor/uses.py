"""What a `uses:` step becomes: inlined steps, a built-in, or an honest skip.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md

Until this file existed, `steps.py` marked EVERY `uses:` step SKIPPED with the
message "needs actions.resolver (Dev A, A17)". A17 landed four sessions ago —
resolver.py and composite.py are complete and unit-tested — so the seam had
outlived the thing it was waiting for, and the demo action we ship ourselves
(`.yeet/actions/checkout`, A19) did nothing when a workflow used it. That is
the fifth instance in this project of a finished module with no call site, and
the handbook rule it breaks is §6: when you finish a module, grep for its call
site.

THREE OUTCOMES, and the difference matters to a user reading a log:

* **inline** — a local or cloned COMPOSITE action. Its steps are spliced into
  the job at the point of the `uses:`, with `with:` mapped to `INPUT_*`. This
  is the one that makes composite actions actually run.

* **builtin** — `actions/upload-artifact`, `download-artifact`, `cache` and
  `checkout`.
  These three do not run as scripts anywhere: on GitHub they are node actions
  talking to a service API that does not exist here. Reimplementing their
  OBSERVABLE behaviour against `storage/` is the only way a real workflow gets
  through them, and it is also what finally gives `storage/artifacts.py` and
  `storage/cache.py` a call site — both were written in session 2 and had
  never been reachable from a run.

* **unsupported** — docker and node actions (C15/C16). Still skipped, but now
  the message says which kind and why, instead of naming a developer and a
  ticket that closed.

TWO LATER ADDITIONS, both of which turned a silent lie into an answer:

`actions/setup-node` and its three siblings used to land in `unsupported`, and
`unsupported` is SKIPPED, and skipped is GREEN. A workflow that asked for node
20 therefore ran on whatever node the image had and passed. They are now
inlined as a probe script — see `actions/toolchain.py` for why checking is the
only honest thing a local runner can offer here, and why it has to happen as a
step inside the container rather than as a built-in on the host.

`owner/repo@ref` now reaches `resolver.resolve_remote()` (A20), which was the
eleventh finished-but-unreachable module here: written, unit-tested, and never
called, so every third-party composite action in existence reported as "could
not be resolved to a local action". Two things had to be true before wiring it
was honest rather than merely possible.

First, it could not fetch what W402 tells you to use. Its `git clone --depth 1
--branch <ref>` cannot check out a commit SHA, so the pinned spelling failed
100% of the time. It goes through `actions/fetch.py` now.

Second, a `uses:` line that reaches the NETWORK mid-run needs a policy, not a
default nobody chose. The one here: fetch on a cache miss and say so on the
line it happens; cache by ref, forever for a SHA or an exact tag and for a day
for a moving `@v4`; and `--offline` to refuse the network entirely and report a
miss against the workflow line that caused it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from yeet.actions import toolchain
from yeet.core.diagnostics import DiagnosticBag
from yeet.core.ir import Step

Kind = Literal["inline", "builtin", "unsupported"]

INLINE: Kind = "inline"
BUILTIN: Kind = "builtin"
UNSUPPORTED: Kind = "unsupported"

#: `actions/cache@v4` -> `actions/cache`. The ref does not change what it does.
_REF = re.compile(r"@.*$")

UPLOAD_ARTIFACT = "actions/upload-artifact"
DOWNLOAD_ARTIFACT = "actions/download-artifact"
CACHE = "actions/cache"
CHECKOUT = "actions/checkout"

BUILTINS = frozenset({UPLOAD_ARTIFACT, DOWNLOAD_ARTIFACT, CACHE, CHECKOUT})


@dataclass(frozen=True, slots=True)
class UsesPlan:
    kind: Kind
    steps: list[Step] = field(default_factory=list)
    builtin: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    blocking: bool = False
    """An UNSUPPORTED step that must FAIL rather than skip.

    Skipped is green, and green has to mean "this would pass on GitHub". A
    docker or node action is skipped-green because we made a considered
    decision not to run it yet; an action we could not GET is a different
    thing entirely — the workflow says to run it, GitHub would run it, and
    calling that a pass is the same false green `--offline` was never meant to
    buy. See `actions/toolchain.py` for the other half of this argument."""


def bare_name(uses: str) -> str:
    """`actions/cache@v4` -> `actions/cache`; `docker://x` unchanged."""
    return _REF.sub("", uses.strip())


def plan_uses(
    step: Step,
    root: Path,
    bag: DiagnosticBag,
    *,
    offline: bool = False,
    on_fetch: Callable[[str], None] | None = None,
) -> UsesPlan:
    """Decide what to do with one `uses:` step. Never raises.

    `bag` collects E313/E314/W319 from the resolver. The caller decides whether
    those block; here they are only recorded.

    `on_fetch` is called with the `uses:` string just before a remote action is
    downloaded, so the step's own log says the network was used and for what.
    `offline` forbids that fetch; a cache hit still resolves normally.
    """
    uses = (step.uses or "").strip()
    if not uses:
        return UsesPlan(kind=UNSUPPORTED, reason="empty `uses:`")

    name = bare_name(uses)
    if name in BUILTINS:
        return UsesPlan(kind=BUILTIN, builtin=name, inputs=dict(step.with_))

    # `setup-node` and its siblings become an inlined probe STEP, not a
    # built-in. A built-in runs in-process on the host; the question is what
    # the CONTAINER provides, and `node --version` on the host of a Docker run
    # answers a different question. See `actions/toolchain.py`.
    if toolchain.is_toolchain(name):
        probe = Step(
            pos=step.pos,
            name=f"{name} (checking, not installing)",
            run=toolchain.probe_script(name, dict(step.with_)),
            shell="sh",
            id=step.id,
            if_=None,
            continue_on_error=step.continue_on_error,
        )
        return UsesPlan(kind=INLINE, steps=[probe])

    if uses.startswith("docker://"):
        return UsesPlan(
            kind=UNSUPPORTED,
            reason=f"`{uses}` is a docker action — not supported yet (C15)",
        )

    from yeet.actions import resolver

    action = resolver.resolve(uses, root, bag)
    if action is None:
        # Not local. `owner/repo@ref` is fetched into the action cache and then
        # resolved from there like any other directory on disk.
        try:
            action = resolver.resolve_remote(uses, bag, offline=offline, on_fetch=on_fetch)
        except resolver.Offline as exc:
            return UsesPlan(
                kind=UNSUPPORTED,
                blocking=True,
                reason=(
                    f"`{uses}` is not in the action cache and `--offline` was given "
                    f"(looked in {exc}). Run once without `--offline` to fetch it."
                ),
            )
    if action is None:
        return UsesPlan(
            kind=UNSUPPORTED,
            reason=f"`{uses}` could not be resolved to a local or remote action",
        )

    if action.kind != "composite":
        # Now an accurate answer rather than "could not be resolved": we
        # fetched it, we read its action.yml, and THIS is the part we cannot
        # run yet. A user chasing C15/C16 can see which one they need.
        return UsesPlan(
            kind=UNSUPPORTED,
            reason=f"`{uses}` is a {action.kind} action — not supported yet "
            f"({'C15' if action.kind == 'docker' else 'C16'})",
        )

    input_env = resolver.apply_inputs(action, dict(step.with_), bag)
    return UsesPlan(
        kind=INLINE, steps=resolver.composite_steps(action, input_env, dict(step.with_))
    )
