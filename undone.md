

# session-9 — the installer's toolchain, parallel logs, W317

## The installer could not do the one thing it most needed to

It required a suitable Python and could only print instructions when there
wasn't one — on a stock macOS box (system Python is 3.9) or a slim container,
that is where it stopped. `uv` is now preferred when present, and the reason is
not its speed: **it can provision a Python.** Verified with no suitable
interpreter on PATH at all — uv fetched 3.14.7 and the whole install took nine
seconds, after which a two-leg matrix with secrets and masking ran green on it.

uv builds OUR virtualenv rather than doing `uv tool install`, so the layout,
the shim and `yeet-uninstall` are identical whichever backend ran. One thing to
remove, in one place, however it got there. Falls back to `python -m venv`
(`YEET_NO_UV=1` forces it), and when neither is possible it now names both
fixes — the apt/brew line and uv, since uv is the shorter path. All three
branches tested.

## Parallel logs were true line by line and useless as a whole

A three-leg matrix printed three identical `+-- setup` headers and then
`using node 16`, `using node 18`, `using node 20` in whatever order the threads
reached the sink. Nothing said which leg any line came from.

Lines now carry a `job │ ` gutter once a run has more than one job, and nothing
before that — a single-job run is exactly as clean as it was, and that is safe
because a line emitted before a second job appeared could only have come from
the first. `grep 'node 18'` is now a complete log for that leg.

Found while fixing it: `_group_depth` was ONE shared counter while jobs emit
from parallel threads, so one job's `::group::` silently indented another
job's output, and either job's `::endgroup::` closed it.

## W317 — every registered code now has an implementation

`::set-output::`, `::save-state::`, `::set-env::`, `::add-path::`. A warning,
not an error, and that is the whole point: these still PARSE and now do
nothing, so a step ending `echo "::set-output name=sha::$(git rev-parse HEAD)"`
runs green on GitHub and produces no value — the job reading
`steps.x.outputs.sha` gets an empty string and fails somewhere else entirely.

The `::` sigil is required so prose about the migration is not flagged, and
current commands (`::group::`, `::add-mask::`, `::error::`) are untouched.
Zero hits across all nine real workflows in `tests/corpus/`.

## The panel had to fit the terminal

A fixed 72-column frame wraps on an 80-column window with anything in the
gutter. A wrapped box does not read as a narrow box, it reads as corruption.
Width now comes from `tput cols`, descriptions truncate to the derived column,
and below ~35 columns the box is dropped for a plain list. Checked at 100, 72,
60 and 40 columns and in the ASCII fallback.

## Still open

- **C15/C16** — docker and node actions are still skipped with a reason.
  `actions/checkout@v4` being a no-op is the user-visible consequence.
- **Built-ins run on the host**, not in the job's container (deliberate; the
  workspace is a bind mount).
- **A git-less install path.** The installer still needs git, because it
  installs from a git URL. A tagged release with a wheel would remove that and
  make "download a file" a real second option.
- **uv picks the newest satisfying Python** — 3.14 on this machine, which is
  ahead of the 3.10–3.13 CI matrix. It worked, but the first interpreter with
  no wheels for a C-extension dependency will find this out the hard way.
  Pinning the request to a tested range is the safer call if that happens.
- **`docs/` overlap** between handbook / understanding-yeet / getting-started.
- **Windows** verified by CI only; the 3.10 leg is new there.

## Verification

    make check        805 passed, six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py (56 rules)

Installer exercised in three environments: uv with no system Python, venv
fallback with uv declined, and neither available (the guidance path).
