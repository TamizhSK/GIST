"""Layer 4 — lint rules. Importing this package is what registers them.

Owner: Dev D
Tier: 3 — may import from: core, expressions, reporting, parser, analyzer
See docs/architecture.md

WHY THIS FILE HAS IMPORTS THAT LOOK UNUSED
------------------------------------------
Rules self-register by calling `register()` at module scope, so a rule module
that nobody imports contributes nothing. This package was empty and the only
import in the product was `from ...layer4_lint.base import run_lints` — which
loads `base` and none of the five rule modules. The result: `RULES == []` at
runtime, `yeet check` printed nothing at all for `actions/checkout@main` (a
W402), and the unit tests still passed because they import the rule classes
directly.

So: importing this package IS the registration step. Import `run_lints` from
here (`from yeet.validation.layer4_lint import run_lints`), never from `.base`,
and a new rule needs one line in `RULE_MODULES` plus the `from . import` below.

`test_lint.py::test_every_rule_module_is_registered` walks this directory and
fails if a rule module exists on disk but is missing here, so the gap cannot
silently reopen.
"""

from __future__ import annotations

from . import naming, pinning, portability, secrets_scan, shell  # noqa: F401
from .base import RULES, LintRule, register, run_lints

#: Every rule module in this package. The test cross-checks it against the
#: directory listing — add a rule module, add it here.
RULE_MODULES = ("naming", "pinning", "portability", "secrets_scan", "shell")

__all__ = ["RULES", "RULE_MODULES", "LintRule", "register", "run_lints"]
