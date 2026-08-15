

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


# session-10 — the runtime, the installer, and what running it found

Four agents were dispatched over disjoint file sets; all four were killed
mid-edit by an account spend limit. Their surviving work was finished by hand
and is recorded here with what they left half-done, because the half-done parts
are the ones that bite.

## The bug that mattered: `runs-on: ${{ matrix.os }}` was never interpolated

Found by running yeet on its OWN CI workflow — a thing that had never been
done, and which took ten seconds to do. The image resolver read `job.runs_on`
RAW, so the literal string reached the runner-label table, matched nothing, and
every leg of a cross-platform matrix died with E315 "not a known runner label
or image". The leg knew its own value the whole time; nothing asked it.

Every cross-platform workflow in existence is written that way, so this was a
hard stop on most real files, and no unit test could have caught it: the tests
build a `Job` with a literal `runs_on`, which is the one case that works.

Expanded per leg on a COPY — the IR is shared across the plan and legs run in
parallel threads, so writing the value back would race and each leg would read
whichever landed last.

A second bug fell out of the first: a `local` leg inside a Docker run tried to
pull an image called "local". `runs-on: ${{ matrix.os }}` over
`[ubuntu-latest, local]` is ONE workflow with both kinds in it, and the backend
is chosen once for the whole run. Host legs now delegate to `LocalBackend`.

## The TUI, from a real screenshot

* **A built-in step never said it had finished.** `_run_builtin` emitted the
  step's output but not its lifecycle, and the live tree resolves a node on
  STEP_END. So `checkout` sat under a spinner for the rest of the run while its
  own result scrolled past above it. Only `run:` steps had ever sent those.
* **The summary panel was 111 columns** of mostly-empty box around two short
  rows, in ASCII `+---+` on a UTF-8 terminal. Capped at 70 — a caller passing
  the console width means "this is the room you have", not "fill it" — with
  box characters chosen by what the STREAM can encode, not by `LANG`, because
  a UTF-8 locale piped into a cp1252 file still raises.
* **The palette reached only the summary.** Job/step lines were still the basic
  sixteen while the summary was truecolour, so the closing line looked like it
  belonged to another program. Every line now goes through `paint()`.

## Docker failures that named the problem

`DockerFailure` and `daemon_is_gone` had been written and never raised — the
ninth instance of the unreachable-module pattern in this repo. Now the path for
every pull, build and create failure, with tables keyed on what the daemon
actually says: unreachable registry, no such image, auth, rate limit, no arm64
build, disk full, socket permissions, Docker Desktop file sharing, a name held
by an interrupted run.

`DockerUnavailable` was being caught per job, so a fourteen-job workflow
printed "cannot reach the daemon" fourteen times and exited 1 — "your workflow
failed". It is not the workflow. It propagates now and exits **3**, and the
message is words rather than docker-py's `('Connection aborted.',
FileNotFoundError(2, ...))`.

## Still open

- **Remote composite actions.** `owner/repo@ref` reports as unresolvable even
  though `resolve_remote` (A20) could fetch it. Deliberate: cloning from a
  `uses:` line reaches the network mid-run and needs its own decision about
  caching and offline behaviour.
- **Windows** is verified by CI only. The 3.10 leg is new there, and the
  encoding-gated panel glyphs have never run on a cp1252 console.
- **A git-less install** works via the GitHub tarball, but only for a GitHub
  URL. A tagged release with a wheel would make "download a file" a first-class
  path rather than a fallback.
- **`docs/` overlap** between handbook / understanding-yeet / getting-started.
- **The daemon dying MID-RUN** is translated but not reproduced end to end;
  `docker kill` of a live container during a step is untested.

## Verification

    make check        808 passed, six gates green
    pytest -m docker  18 passed against a live daemon
    make rules-check  docs/rules.md matches codes.py

Exercised by hand: a mixed `[ubuntu-latest, local]` matrix (both legs green),
checkout of a tag into `path:` via host git AND via a git container with git
removed from PATH, a toolchain mismatch failing loudly, DOCKER_HOST pointed at
a dead socket (exit 3, two lines, no traceback), and a full install from an
empty `$HOME` on a real pty.
