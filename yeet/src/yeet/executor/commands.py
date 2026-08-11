"""Parse ::group:: ::error:: ::add-mask:: etc from stdout.

This is how a step talks back to the runner: it prints a specially-shaped line
and we act on it. It is genuinely how GitHub's runner works, and it is what
makes `::add-mask::` possible at all — a step can discover a secret at runtime
(a token minted by a login command) and have it redacted from that point on.

Nothing here may raise. It runs on every line of every step's output, and an
unparseable line is not an error — it is just output.

Owner: Dev C
Tier: 5 — may import from: everything below tier 5
See docs/architecture.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

MARKER = "::"

GROUP = "group"
ENDGROUP = "endgroup"
ERROR = "error"
WARNING = "warning"
NOTICE = "notice"
ADD_MASK = "add-mask"
DEBUG = "debug"

KNOWN = frozenset({GROUP, ENDGROUP, ERROR, WARNING, NOTICE, ADD_MASK, DEBUG})

DEPRECATED = frozenset({"set-output", "save-state", "set-env"})
"""Superseded by the $GITHUB_OUTPUT / $GITHUB_STATE / $GITHUB_ENV files in
architecture.md 3.6. We still parse them so old actions do not silently break;
W411 is Dev D's lint that tells the user to stop writing them."""

# GitHub escapes these inside command properties and values, because the
# delimiters are structural. Decoding is not optional: an `::error::` whose
# message contains a colon arrives mangled otherwise.
_UNESCAPE = (
    ("%0D", "\r"),
    ("%0A", "\n"),
    ("%3A", ":"),
    ("%2C", ","),
    ("%25", "%"),  # last: a literal %25 must not be re-expanded
)


@dataclass(frozen=True, slots=True)
class Command:
    """One `::name key=value::value` directive."""

    name: str
    value: str = ""
    params: dict[str, str] = field(default_factory=dict)

    @property
    def is_known(self) -> bool:
        return self.name in KNOWN

    @property
    def is_deprecated(self) -> bool:
        return self.name in DEPRECATED


def unescape(text: str) -> str:
    for token, char in _UNESCAPE:
        text = text.replace(token, char)
    return text


def parse_workflow_command(line: str) -> Command | None:
    """`::group::Installing` -> Command("group", "Installing").

    Returns None for anything that is not a directive, which is the
    overwhelming majority of lines. Never raises.
    """
    stripped = line.strip()
    if not stripped.startswith(MARKER):
        return None

    body = stripped[len(MARKER) :]
    head, sep, value = body.partition(MARKER)
    if not sep:
        # `::endgroup::` with the trailing marker omitted is common in the wild.
        head, value = body, ""
    head = head.strip()
    if not head:
        return None

    name, _, param_text = head.partition(" ")
    name = name.strip().lower()
    if not name:
        return None

    params: dict[str, str] = {}
    for chunk in param_text.split(","):
        key, eq, val = chunk.partition("=")
        if eq and key.strip():
            params[key.strip()] = unescape(val.strip())

    return Command(name=name, value=unescape(value), params=params)
