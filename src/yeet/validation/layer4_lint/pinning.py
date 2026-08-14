"""Lint rules for pinning and action versions (W402, W403, W411, W412).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

import re
from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.validation.layer4_lint.base import register

#: Refs that are re-pointed in place, so `uses: x@main` is a different action
#: tomorrow than it is today.
_MOVING_REFS = frozenset({"main", "master", "head", "latest"})

#: `@v4` is also a moving ref — GitHub's convention is that the major tag is
#: re-pointed at every minor release. It was previously a hardcoded ("v1", "v2")
#: list, which quietly let `@v3` and up through for no stated reason.
_MAJOR_VERSION_REF = re.compile(r"v\d+")


class PinningRule:
    code = "YEET-W402"

    def check(self, wf: Workflow, path: Path) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        for job_id, job in wf.jobs.items():
            # W403 is about a CONTAINER IMAGE that floats — `container: node:latest`
            # or an image with no tag at all, which Docker resolves to :latest.
            #
            # It deliberately does NOT look at `runs-on`/`cooked_on`. This rule
            # used to fire on `runs-on: ubuntu-latest`, which is a runner LABEL,
            # not an image reference — it is the value GitHub documents, the one
            # in plan.md's own walking skeleton, and the one in nearly every
            # workflow on earth. A lint that fires on the recommended spelling of
            # the most common field is noise, and noisy lints get switched off
            # wholesale, taking W404 (hardcoded secrets) down with them.
            image = job.container_image
            if image and (image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1]):
                diags.append(
                    Diagnostic(
                        code="YEET-W403",
                        severity=Severity.WARNING,
                        message=f"Job `{job_id}` runs in container image `{image}`, "
                        f"which floats to the newest build",
                        file=path,
                        pos=job.pos or Position(line=0, col=0),
                        help="Pin the image to a specific tag or digest so a rerun "
                        "of this workflow gets the same container",
                    )
                )

            for step in job.steps:
                if step.uses:
                    ref = step.uses.split("@")[-1] if "@" in step.uses else ""
                    if ref in _MOVING_REFS or _MAJOR_VERSION_REF.fullmatch(ref):
                        diags.append(
                            Diagnostic(
                                code="YEET-W402",
                                severity=Severity.WARNING,
                                message=f"Action `{step.uses}` is pinned to moving ref `@{ref}`",
                                file=path,
                                pos=step.pos or Position(line=0, col=0),
                                help="Pin action to full commit SHA for reproducible builds",
                            )
                        )

                if step.run:
                    for line in step.run.splitlines():
                        if any(c in line for c in ("::set-output", "::save-state", "::set-env")):
                            diags.append(
                                Diagnostic(
                                    code="YEET-W411",
                                    severity=Severity.WARNING,
                                    message="Deprecated workflow command in step run",
                                    file=path,
                                    pos=step.pos or Position(line=0, col=0),
                                    help="Use `$GITHUB_OUTPUT` or `$GITHUB_ENV` files instead",
                                )
                            )

        return diags


register(PinningRule())
