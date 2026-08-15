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

`owner/repo@ref` still reaches `resolver.resolve()`, which only answers about
LOCAL paths, so a remote composite action is reported as unresolvable even
though `resolver.resolve_remote()` (A20) could fetch it. That is the next
call site to wire, and it is deliberately not wired here: cloning from a
`uses:` line reaches the network mid-run, which needs its own decision about
caching and offline behaviour.
"""

from __future__ import annotations

import re
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


def bare_name(uses: str) -> str:
    """`actions/cache@v4` -> `actions/cache`; `docker://x` unchanged."""
    return _REF.sub("", uses.strip())


def plan_uses(step: Step, root: Path, bag: DiagnosticBag) -> UsesPlan:
    """Decide what to do with one `uses:` step. Never raises.

    `bag` collects E313/E314/W319 from the resolver. The caller decides whether
    those block; here they are only recorded.
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
        return UsesPlan(
            kind=UNSUPPORTED,
            reason=f"`{uses}` could not be resolved to a local action",
        )

    if action.kind != "composite":
        return UsesPlan(
            kind=UNSUPPORTED,
            reason=f"`{uses}` is a {action.kind} action — not supported yet "
            f"({'C15' if action.kind == 'docker' else 'C16'})",
        )

    input_env = resolver.apply_inputs(action, dict(step.with_), bag)
    return UsesPlan(kind=INLINE, steps=resolver.composite_steps(action, input_env))
