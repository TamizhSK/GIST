"""Lint rules for pinning and action versions (W402, W403, W411, W412).

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

from yeet.core.diagnostics import Diagnostic, Position, Severity
from yeet.core.ir import Workflow
from yeet.core.refs import is_moving
from yeet.validation.layer4_lint.base import register

# Which refs move lives in `core/refs.py`, not here. The resolver's action
# cache asks the same question — whether `@v4` may be reused forever — and it
# sits at tier 2, which may not import this module. Two copies of the list
# would have been free to drift with nothing able to fail when they did.


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
                    if ref and is_moving(ref):
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
