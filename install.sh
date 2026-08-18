#!/bin/sh
# yeet installer — Linux, macOS, and WSL.
#
#   curl -fsSL https://raw.githubusercontent.com/TamizhSK/YEET/main/install.sh | sh
#
# What it does: finds a Python 3.10+, builds a virtualenv that belongs to yeet
# alone, installs yeet and its dependencies into it, and drops a launcher on
# your PATH. It never installs into your system Python and never touches a
# project's virtualenv — a CI runner that breaks your project's dependencies
# to install itself has failed before it starts.
#
# POSIX sh on purpose: /bin/sh is dash on Debian and Ubuntu (so also on most of
# WSL), and bashisms here would fail on exactly the machines this targets.
#
# Run from a clone, it installs THAT clone — `./install.sh` inside a checkout
# you have been editing means the checkout, not `main` off the network.
#
# Options (after `--` when piped:  ... | sh -s -- --version v0.5):
#   --version <ref>   install a tag, branch or commit from GitHub instead
#   --local           install from THIS clone (the default when there is one)
#   --help
#
# Environment:
#   YEET_REPO      git URL to install from      (default: the GitHub repo)
#   YEET_REF       branch, tag or commit        (default: main)
#   YEET_HOME      where the venv lives         (default: ~/.local/share/yeet)
#   YEET_BIN_DIR   where the launcher goes      (default: ~/.local/bin)
#   YEET_NO_MODIFY_PATH=1   don't offer to edit your shell profile

set -eu

# Everything below defaults into $HOME. Unset, `set -u` kills the script with
# "HOME: parameter not set" at whichever line touches it first, which tells the
# user nothing about what to do. Say it once, up front, in words.
if [ -z "${HOME:-}" ]; then
    printf '%s\n' "HOME is not set, so there is nowhere to install to." >&2
    printf '%s\n' "Set HOME, or point YEET_HOME and YEET_BIN_DIR somewhere writable." >&2
    exit 1
fi

REPO="${YEET_REPO:-https://github.com/TamizhSK/YEET}"
REF="${YEET_REF:-main}"
HOME_DIR="${YEET_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/yeet}"
BIN_DIR="${YEET_BIN_DIR:-$HOME/.local/bin}"
MIN_MINOR=10
MAX_TESTED=13   # the newest minor the CI matrix actually runs

# `$SHELL` is NOT guaranteed to exist. A Docker image, a cron job, a CI step and
# `su - <user>` on some systems all run with it unset, and `${SHELL##*/}` under
# `set -u` is a fatal "SHELL: parameter not set" — which is exactly how this
# installer died at the last step, after having already done all of its work.
#
# `set -u` is worth keeping, so the shell name is read ONCE, here, with a
# default. /bin/sh is the honest fallback: if we cannot tell what shell this is,
# the POSIX profile is the right guess.
SHELL_NAME="${SHELL:-/bin/sh}"
SHELL_NAME="${SHELL_NAME##*/}"
TOTAL_STEPS=4
LOCAL_DIR=''
AUTO_LOCAL=0        # did we find the clone ourselves, or were we told?
#: Was a specific ref ASKED for? `REF` always has a value (`main`), so the
#: default is indistinguishable from a choice unless we record the choice.
#: Asking for a ref means "install that ref from GitHub", which is the one
#: thing the clone next to the script is definitely not.
REF_EXPLICIT=0
[ -n "${YEET_REF:-}" ] && REF_EXPLICIT=1
[ -n "${YEET_REPO:-}" ] && REF_EXPLICIT=1

#: Whether a terminal can RENDER U+2588 depends on its font, and no process can
#: ask a terminal what font it is using. Every automatic check here is about the
#: ENCODING, which is a different question — so there has to be a stated way out
#: for someone whose terminal defeats it, or the only way out is a bug report.
#: The environment variable is what `curl | sh` needs; that form takes no flags.
ASCII_FORCED=0
[ -n "${YEET_ASCII:-}" ] && ASCII_FORCED=1

#: `-v` puts the transcript back on a terminal. The bar is the right default and
#: it costs exactly one thing: when an install HANGS rather than fails, a
#: percentage with no history cannot be reported usefully.
VERBOSE=0
SELFTEST=0

usage() {
    cat <<'USAGE'
yeet installer

  curl -fsSL https://raw.githubusercontent.com/TamizhSK/YEET/main/install.sh | sh

Run from a clone, it installs that clone. No flag needed:

  ./install.sh

Options:
  --version <ref>   a tag, branch or commit from GitHub (default: main)
  --local           install from the clone this script sits in — the default
                    already, when it sits in one
  --ascii           draw the wordmark and the bar with `#` (YEET_ASCII=1 too)
  --verbose, -v     print every step instead of one progress bar
  --help            this text
USAGE
}

# Reproducibility and demo insurance. Pinning a version is the difference
# between "install yeet" and "install the same yeet the docs describe", and
# `--local` is the path that still works when the venue's wifi does not.
while [ $# -gt 0 ]; do
    case "$1" in
        --version) [ $# -ge 2 ] || { usage >&2; exit 2; }; REF="$2"; REF_EXPLICIT=1; shift 2 ;;
        --version=*) REF="${1#--version=}"; REF_EXPLICIT=1; shift ;;
        --local)
            # `dirname "$0"` is meaningless under `curl | sh` — there $0 is `sh`
            # and no script exists on disk to install from.
            #
            # Test for the FILE, not for a slash: `sh install.sh --local` sets
            # $0 to a bare `install.sh`, which has no slash and is nonetheless
            # a real file in $PWD. Keying off the slash rejected it and printed
            # advice to do the thing the user had just done.
            if [ -f "$0" ]; then
                LOCAL_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
            else
                printf '%s\n' "--local needs the script on disk: clone, then ./install.sh --local" >&2
                exit 2
            fi
            shift ;;
        # Draw the presentation layer and exit, so the bar's invariants can be
        # asserted in milliseconds instead of by running a 35-second install.
        # Deliberately absent from `usage`: it is a test hook, not a feature.
        --selftest) SELFTEST=1; shift ;;
        --ascii) ASCII_FORCED=1; shift ;;
        --verbose|-v) VERBOSE=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

# THE CLONE IS THE DEFAULT when the script is sitting in one. `--local` was a
# flag you had to already know existed: running `./install.sh` inside a clone
# you had just edited went to the network and installed `main` instead, which
# is never what that command means. So detect it.
#
# Silent on every failed check, unlike explicit `--local` — this path runs for
# `curl | sh` too, where none of it applies, and auto-detection that can fail
# an install is worse than no auto-detection. `--local` stays for CI and for
# saying it out loud; it now asks for what would have happened anyway.
if [ -z "$LOCAL_DIR" ] && [ "$REF_EXPLICIT" = 0 ] && [ -f "$0" ]; then
    CANDIDATE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd 2>/dev/null) || CANDIDATE=''
    # `name = "yeet"` and not merely "a pyproject.toml exists": install.sh
    # copied into an unrelated project must not install that project.
    if [ -n "$CANDIDATE" ] && grep -q '^name = "yeet"' "$CANDIDATE/pyproject.toml" 2>/dev/null; then
        LOCAL_DIR="$CANDIDATE"
        AUTO_LOCAL=1
    fi
fi

# ── presentation ──────────────────────────────────────────────────────────────
# Two independent questions, and conflating them is the usual bug: "may I use
# colour" (a terminal, and NO_COLOR unset) and "may I use box-drawing
# characters" (a UTF-8 locale). A UTF-8 pipe still wants no ANSI; an ASCII
# terminal still wants colour. They are decided separately below.

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
    TTY=1
    ESC=$(printf '\033')
    N="${ESC}[0m";      B="${ESC}[1m";      D="${ESC}[2m"
    ACCENT="${ESC}[38;5;209m"                 # warm amber, the brand colour
    G="${ESC}[38;5;114m"; Y="${ESC}[38;5;221m"; R="${ESC}[38;5;203m"
    MUTE="${ESC}[38;5;245m"
else
    TTY=0
    ESC=''; N=''; B=''; D=''; ACCENT=''; G=''; Y=''; R=''; MUTE=''
fi

case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]8*|*[Uu][Tt][Ff]-8*) UNICODE=1 ;;
    *)                                UNICODE=0 ;;
esac
[ "$ASCII_FORCED" = 1 ] && UNICODE=0

if [ "$UNICODE" = 1 ]; then
    TL='╭'; TR='╮'; BL='╰'; BR='╯'; HZ='─'; VT='│'
    TICK='✔'; CROSS='✘'; WARN_G='▲'; ARROW='→'; DOT='●'
else
    TL='+'; TR='+'; BL='+'; BR='+'; HZ='-'; VT='|'
    TICK='ok'; CROSS='xx'; WARN_G='!'; ARROW='->'; DOT='*'
fi

say()  { printf '%s\n' "$*"; }
rule() { i=0; s=''; while [ "$i" -lt "$1" ]; do s="$s$HZ"; i=$((i + 1)); done; printf '%s' "$s"; }

# The wordmark, in the sunset the README's logo uses: indigo at the top of the
# letters, magenta through the middle, the low sun at the baseline. Six rows of
# the same block art, one colour per row.
#
# Unicode is gated on the LOCALE, not on having a terminal. A tty with a
# latin-1 locale is a real configuration — an old ssh session, a container with
# no locale set — and printing block characters into it produces mojibake,
# which is a worse first impression than plain text. `TTY` says "may I use
# colour"; `UNICODE` says "may I use these characters". They are different
# questions and this used to conflate them.
_BAND_1='38;5;62'    # indigo
_BAND_2='38;5;97'    # violet
_BAND_3='38;5;133'   # magenta
_BAND_4='38;5;168'   # rose
_BAND_5='38;5;209'   # coral, the brand accent
_BAND_6='38;5;215'   # the low sun

banner() {
    [ "$TTY" = 0 ] && { say "yeet installer"; say ""; return; }
    # The wordmark in whichever alphabet this terminal can render. `█` is
    # U+2588, so the block form needs a UTF-8 locale — and `LANG` unset is a
    # ROUTINE macOS configuration (Terminal.app with "set locale variables"
    # off, an ssh session, `sudo`, cron), not an exotic one. Gating the only
    # logo on it meant the installer greeted a lot of people with one line of
    # spaced-out capitals, which is not a wordmark.
    #
    # So the same six rows exist in ASCII. Colour is unaffected either way —
    # ANSI escapes are themselves ASCII, and the gradient is the point.
    if [ "$UNICODE" = 1 ]; then
        _R1='████     ████  █████████  █████████  █████████████'
        _R2=' ████   ████   ████       ████            ████    '
        _R3='  ████ ████    ███████    ███████         ████    '
        _R4='   ███████     ███████    ███████         ████    '
        _R5='     ████      ████       ████            ████    '
        _R6='     ████      █████████  █████████       ████    '
    else
        _R1='####     ####  #########  #########  #############'
        _R2=' ####   ####   ####       ####            ####    '
        _R3='  #### ####    #######    #######         ####    '
        _R4='   #######     #######    #######         ####    '
        _R5='     ####      ####       ####            ####    '
        _R6='     ####      #########  #########       ####    '
    fi
    say ""
    printf '  %s%s%s\n' "${ESC}[${_BAND_1}m" "$_R1" "$N"
    printf '  %s%s%s\n' "${ESC}[${_BAND_2}m" "$_R2" "$N"
    printf '  %s%s%s\n' "${ESC}[${_BAND_3}m" "$_R3" "$N"
    printf '  %s%s%s\n' "${ESC}[${_BAND_4}m" "$_R4" "$N"
    printf '  %s%s%s\n' "${ESC}[${_BAND_5}m" "$_R5" "$N"
    printf '  %s%s%s\n' "${ESC}[${_BAND_6}m" "$_R6" "$N"
    printf '\n  %sa local GitHub Actions runner, with a dialect of its own%s\n\n' "$MUTE" "$N"
}

# ── the progress bar ──────────────────────────────────────────────────────────
# One bar, pinned to the LAST line, with the log scrolling above it. That
# ordering is the whole trick: a bar printed above its own log is pushed off
# the top by the first thing that happens after it, so the bar goes last and
# every log line is written by erasing it, printing, and drawing it again.
#
# It replaces a spinner that said only "something is happening". On a slow
# network the pip step can sit for a minute, and the question a person is
# actually asking then is "how much of this is left".
#
# TTY only. Into a pipe or a CI log this whole mechanism degrades to the plain
# line-per-event output it had before — carriage returns in a log file are
# noise, and the log is the artifact there.
PCT=0
BAR_ON=0
BAR_LABEL=''

# Known here rather than at the panel far below, because the bar is measured
# from it and the bar runs long before that point.
#
# ASKED THROUGH FD 2, and that is the whole subtlety. Command substitution
# gives the inner command a PIPE for stdout, so `tput cols` cannot see a
# terminal there and quietly answers with the terminfo default — 80 — on a
# window of any size. Every bar came out 69 columns wide. stderr is still the
# terminal inside `$( )`, so that is what gets measured.
#
# `stty size` first because it reads the live window; `tput cols` second
# because busybox stty is not guaranteed to have `size`; $COLUMNS third
# because an interactive shell keeps it current; 80 last because every
# terminal is at least that.
# FOUR RUNGS, because each one is redirectable and the next one is what covers
# it. `./install.sh 2>log` takes out fd 2; a container with no controlling
# terminal takes out /dev/tty; a non-interactive shell does not export
# $COLUMNS. 80 is the floor every terminal has met since 1978.
#
# `<&2` BEFORE `2>/dev/null` on the first rung, and the order is not cosmetic:
# redirections are applied left to right, so silencing stderr first and then
# duplicating it into stdin hands `stty` /dev/null to measure. That bug is why
# every bar was 69 columns wide on a window of any size.
measure_cols() {
    _c=''
    if [ "$TTY" = 1 ]; then
        _c=$(stty size <&2 2>/dev/null | awk '{print $2}') || _c=''
        [ -n "$_c" ] || _c=$(stty size </dev/tty 2>/dev/null | awk '{print $2}') || _c=''
        [ -n "$_c" ] || _c=$(tput cols <&2 2>/dev/null) || _c=''
    fi
    case "$_c" in ''|*[!0-9]*) _c="${COLUMNS:-80}" ;; esac
    case "$_c" in ''|*[!0-9]*) _c=80 ;; esac
    printf '%s' "$_c"
}
COLS=$(measure_cols)

#: Re-measured every Nth frame rather than every frame or never. Every frame is
#: a `stty` process ten times a second; never means a window resized mid-install
#: draws at the old width until the run ends. Ten frames is about a second.
BAR_REMEASURE_EVERY=10
BAR_FRAME=0

#: Everything on the bar's line that is not the bar itself: two leading spaces,
#: `[`, `]`, a space, `100%`, and a space of slack at the right so a full bar
#: never touches the last column — which is where a terminal decides to wrap.
BAR_CHROME=11

if [ "$UNICODE" = 1 ]; then
    _FULL='█'; _EMPTY='░'
else
    _FULL='#'; _EMPTY='-'
fi

#: The bar is drawn only when there is a terminal AND the user has not asked
#: for the transcript. `-v` is the two of them apart: a terminal that prints
#: every line, which is what you want the moment an install misbehaves.
bar_on() { [ "$TTY" = 1 ] && [ "$VERBOSE" = 0 ]; }

bar_draw() {
    bar_on || return 0
    [ $# -gt 0 ] && BAR_LABEL="$1"

    BAR_FRAME=$((BAR_FRAME + 1))
    if [ "$((BAR_FRAME % BAR_REMEASURE_EVERY))" = 0 ]; then COLS=$(measure_cols); fi

    # Full width, less the chrome, less a FIXED field for the label. Fixed
    # because a field that sizes to its contents makes the bar itself change
    # length every time the label does, and a bar that twitches while the
    # percentage stands still looks like the percentage is wrong.
    #
    # Under 60 columns the label is dropped instead of squeezed: a split pane
    # gets a bar it can read rather than a bar and four letters of a word.
    _room=$((COLS - BAR_CHROME))
    _lw=0
    if [ "$COLS" -ge 60 ]; then
        _lw=26
        [ "$((COLS / 3))" -lt "$_lw" ] && _lw=$((COLS / 3))
    fi
    _w=$((_room - _lw - 2))
    if [ "$_w" -lt 10 ]; then _lw=0; _w=$_room; fi
    [ "$_w" -lt 10 ] && _w=10

    # THE SUNSET, TURNED ON ITS SIDE. The wordmark runs indigo at the top of
    # the letters to the low sun at their baseline; the bar runs the same six
    # bands left to right, so the thing filling up is visibly the same object
    # as the thing above it. One escape per band, not per cell — six writes a
    # frame rather than a hundred and twenty.
    _fill=$((PCT * _w / 100))
    _i=0; _bar=''; _band=-1
    while [ "$_i" -lt "$_w" ]; do
        if [ "$_i" -lt "$_fill" ]; then
            _b=$((_i * 6 / _w))
            if [ "$_b" != "$_band" ]; then
                _band=$_b
                case $_b in
                    0) _bar="$_bar${ESC}[${_BAND_1}m" ;;
                    1) _bar="$_bar${ESC}[${_BAND_2}m" ;;
                    2) _bar="$_bar${ESC}[${_BAND_3}m" ;;
                    3) _bar="$_bar${ESC}[${_BAND_4}m" ;;
                    4) _bar="$_bar${ESC}[${_BAND_5}m" ;;
                    *) _bar="$_bar${ESC}[${_BAND_6}m" ;;
                esac
            fi
            _bar="$_bar$_FULL"
        else
            if [ "$_band" != "-2" ]; then _band=-2; _bar="$_bar$D"; fi
            _bar="$_bar$_EMPTY"
        fi
        _i=$((_i + 1))
    done

    if [ "$_lw" -gt 0 ]; then
        # The label is what turns "stuck at 63%" into "stuck at 63% —
        # resolving and downloading", which is the difference between a bug
        # report we can act on and one we cannot.
        _shown=$(printf '%.*s' "$_lw" "$BAR_LABEL")
        printf '\r  %s[%s%s]%s %s%3d%%%s  %s%s%s%s' \
            "$D" "$_bar" "$D" "$N" "$B" "$PCT" "$N" \
            "$MUTE" "$_shown" "$N" "${ESC}[K"
    else
        printf '\r  %s[%s%s]%s %s%3d%%%s%s' \
            "$D" "$_bar" "$D" "$N" "$B" "$PCT" "$N" "${ESC}[K"
    fi
    BAR_ON=1
}

bar_clear() {
    [ "$BAR_ON" = 1 ] || return 0
    printf '\r%s' "${ESC}[K"
    BAR_ON=0
}

# Leave a finished bar in the scrollback rather than erasing it — "100%" is the
# receipt that the thing completed.
bar_finish() {
    bar_on || return 0
    PCT=100
    bar_draw
    printf '\n'
    BAR_ON=0
}

# Ctrl-C IS A NORMAL WAY TO LEAVE AN INSTALLER, and it must not leave the
# terminal mid-frame. Without this the shell prompt lands on top of a half
# painted bar, and any cursor state the bar set is never given back.
#
# `tput cnorm` is belt and braces: this bar never hides the cursor, but the
# rule is that whoever might have changed it restores it, and a Ctrl-C that
# leaves an invisible cursor gets blamed on the terminal rather than on us.
# 130 is the conventional status for SIGINT (128 + 2).
on_interrupt() {
    bar_clear
    [ "$TTY" = 1 ] && { tput cnorm 2>/dev/null || true; }
    printf '\n%s%s interrupted%s\n' "$Y" "$WARN_G" "$N" >&2
    exit 130
}
trap on_interrupt INT
trap on_interrupt TERM

# Every log writer erases the bar, prints its line, and puts the bar back.
# ON A TERMINAL, THE BAR IS THE WHOLE REPORT. `step` and `ok` and `info` do not
# print a line; they retitle the bar, and it is the one thing on screen under
# the wordmark. A four-step install narrating fifteen lines of its own
# bookkeeping is telling you what it is doing instead of showing you how far
# along it is, and the lines are gone from your attention a second later
# anyway.
#
# INTO A PIPE, ALL OF IT PRINTS. That is where the transcript has to be
# complete: a CI log, a redirect someone pastes into an issue, `install.log`.
# The bar is the thing that cannot survive there, and the log is the thing that
# cannot survive on the terminal, so each medium gets the one it can keep.
#
# `warn` and `die` print in BOTH. A warning that scrolled past inside a
# progress bar was never delivered.
STEP_NO=0
step() {
    STEP_NO=$((STEP_NO + 1))
    # A FLOOR, never an assignment. Step 4 begins at 75% by this arithmetic and
    # step 3 has usually crept past 85 by the time it is reached, so setting it
    # outright ran the bar backwards — which reads as the installer losing its
    # place rather than as a change of phase. Progress only ever goes forward.
    _floor=$(((STEP_NO - 1) * 100 / TOTAL_STEPS))
    if [ "$_floor" -gt "$PCT" ]; then PCT="$_floor"; fi
    if ! bar_on; then
        printf '%s[%s/%s]%s %s\n' "$ACCENT" "$STEP_NO" "$TOTAL_STEPS" "$N" "$*"
        return 0
    fi
    bar_draw "$*"
}
ok() {
    if ! bar_on; then printf '      %s%s%s %s\n' "$G" "$TICK" "$N" "$*"; return 0; fi
    bar_draw "$*"
}
info() {
    if ! bar_on; then printf '      %s%s%s\n' "$MUTE" "$*" "$N"; return 0; fi
    bar_draw "$*"
}
warn()  { bar_clear; printf '      %s%s%s %s\n' "$Y" "$WARN_G" "$N" "$*"; bar_draw; }
die()   { bar_clear; printf '\n  %s%s %s%s\n\n' "$R" "$CROSS" "$*" "$N" >&2; exit 1; }

# Runs a command with a spinner, keeping its output for the failure path only.
# The success path stays quiet on purpose: pip's resolver output is 40 lines of
# noise nobody reads, right up until it fails and every one of them matters.
# POSIX only requires `sleep` to accept an INTEGER. GNU and busybox both take
# fractions, so this is a fraction almost everywhere and one second on the
# strict shells where a spinner is cosmetic anyway — better a slow spinner than
# a log full of "sleep: invalid number".
_TICK=0.1
sleep 0.1 2>/dev/null || _TICK=1

# spin LABEL TARGET_PCT COMMAND...
#
# Runs COMMAND with the bar creeping toward TARGET_PCT while it works, and
# lands exactly on TARGET_PCT when it returns. The creep stops one short of the
# target on purpose: a bar that reaches its mark before the work is done is
# lying, and the last percent is what says "this step finished" rather than
# "this step is nearly finished".
#
# On failure the bar goes back to where the step started, so a retried step
# does not appear to have made progress it did not make.
spin() {
    _label="$1"; _target="$2"; shift 2
    if ! bar_on; then
        info "$_label..."
        "$@" >"$HOME_DIR/install.log" 2>&1 || return 1
        PCT="$_target"
        return 0
    fi
    _was="$PCT"
    "$@" >"$HOME_DIR/install.log" 2>&1 &
    _pid=$!
    _ticks=0
    bar_draw "$_label"
    while kill -0 "$_pid" 2>/dev/null; do
        sleep "$_TICK"
        _ticks=$((_ticks + 1))
        # One percent per half second at the usual 0.1s tick. Slow enough that
        # a 40-second pip install does not run out of bar, and fast enough to
        # be visibly moving.
        if [ "$((_ticks % 5))" = 0 ] && [ "$PCT" -lt "$((_target - 1))" ]; then
            PCT=$((PCT + 1))
        fi
        bar_draw "$_label"
    done
    if ! wait "$_pid"; then
        PCT="$_was"
        bar_draw "$_label"
        return 1
    fi
    PCT="$_target"
    bar_draw "$_label"
    return 0
}

banner

# The test hook (`--selftest`). Everything above this line is presentation;
# everything below it touches the disk. Sitting exactly here is what lets a
# test exercise the real drawing code without a real install.
if [ "$SELFTEST" = 1 ]; then
    step "Checking prerequisites"
    ok "python 3.13.12 (/usr/bin/python3)"
    for _p in 0 25 50 82; do
        PCT=$_p
        bar_draw "resolving and downloading"
    done
    warn "a warning drawn while the bar was on screen"
    bar_finish
    say "selftest done"
    exit 0
fi

# ── before anything is installed ──────────────────────────────────────────────
# SAID FIRST, not in the summary, because by the summary it is advice about
# something the reader has already finished doing. Someone installing a
# workflow runner is about to run a workflow, and the daemon takes a minute to
# come up — that minute is better spent now than after `yeet run` has already
# failed once.
#
# Precise about what needs it: the INSTALL does not, and saying it does would
# be a lie that turns a working offline install into a support question. `yeet
# run` does, for every job that is not `cooked_on: local`.
#
# Never fatal, and never a prompt. `curl | sh` has the script on stdin, so
# there is nobody to answer one.
preflight_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        printf '  %s%s%s  Docker is not installed.\n' "$Y" "$WARN_G" "$N"
        printf '     %sInstalling yeet does not need it. Running a workflow does —\n' "$MUTE"
        printf '     without it only `cooked_on: local` jobs will run.%s\n\n' "$N"
        return 0
    fi
    if docker info >/dev/null 2>&1; then
        printf '  %s%s%s  Docker is running — container jobs will work.%s\n\n' \
            "$G" "$TICK" "$MUTE" "$N"
        return 0
    fi
    printf '  %s%s%s  %sStart Docker Desktop now, and leave it running.%s\n' \
        "$Y" "$WARN_G" "$N" "$B" "$N"
    printf '     %syeet runs each job in a container. The install below does not\n' "$MUTE"
    printf '     need the daemon, but `yeet run` does — starting it now means it\n'
    printf '     is ready by the time the install finishes.%s\n\n' "$N"
}
preflight_docker

# ── 1. what we will build the environment with ────────────────────────────────
# Two backends, and `uv` is preferred where it exists for a reason that matters
# more than its speed: it can PROVISION a Python. On a box whose only
# interpreter is the 3.9 macOS ships, or a slim container with none at all, the
# venv path can only tell the user to go and install one; uv downloads a
# managed interpreter and carries on. That is the difference between a tool
# that sets itself up and one that prints instructions.
#
# uv builds OUR virtualenv rather than doing `uv tool install`, so the layout,
# the shim, and `yeet-uninstall` are identical whichever backend ran — one
# thing to remove, in one place, no matter how it got there.

# Newest first: a box with 3.10 and 3.13 should use 3.13. `python` is checked
# last because on an old machine it is still Python 2, and the version probe
# below is what rejects it rather than a crash three steps later.
find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" 2>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

step "Checking prerequisites"

PYTHON=$(find_python || true)
if command -v uv >/dev/null 2>&1 && [ -z "${YEET_NO_UV:-}" ]; then
    BACKEND=uv
    ok "uv $(uv --version 2>/dev/null | awk '{print $2}') ${MUTE}(fast path)${N}"
    if [ -n "$PYTHON" ]; then
        ok "python $("$PYTHON" -c 'import platform; print(platform.python_version())')"
    else
        info "no suitable Python on PATH — uv will fetch one"
    fi
elif [ -n "$PYTHON" ]; then
    BACKEND=venv
    ok "python $("$PYTHON" -c 'import platform; print(platform.python_version())') ${MUTE}($PYTHON)${N}"
    # `python3-venv` is a separate package on Debian and Ubuntu, so a working
    # python3 does NOT imply a working `-m venv`. Finding that out here, with
    # the apt line that fixes it, beats a stack trace halfway through.
    "$PYTHON" -c "import venv" 2>/dev/null || die "this Python cannot create virtualenvs.

      Debian/Ubuntu/WSL   sudo apt install python3-venv"
    ok "venv available"
else
    die "no Python 3.$MIN_MINOR or newer, and no uv to fetch one.

      Debian/Ubuntu/WSL   sudo apt install python3 python3-venv
      Fedora              sudo dnf install python3
      macOS               brew install python@3.12

      or install uv, which brings its own Python:
      curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# git is PREFERRED, not required. A `git+` URL needs it; a source tarball does
# not, and GitHub serves one for every branch and tag. That matters on the
# machines this script is most likely to meet: a slim container image, or a
# corporate box where installing git is a ticket rather than a command.
if [ -n "$LOCAL_DIR" ]; then
    [ -f "$LOCAL_DIR/pyproject.toml" ] || die "--local: no pyproject.toml in $LOCAL_DIR"
    SOURCE="$LOCAL_DIR"
    if [ "$AUTO_LOCAL" = 1 ]; then
        # Named, not silent. Installing something other than what the user
        # thinks is the worst outcome available here, so the choice we made on
        # their behalf is on screen with the way to override it.
        ok "installing from this clone ${MUTE}($LOCAL_DIR)${N}"
        info "${MUTE}pass --version <ref> to install from GitHub instead${N}"
    else
        ok "installing from this clone ${MUTE}($LOCAL_DIR)${N}"
    fi
elif command -v git >/dev/null 2>&1; then
    SOURCE="git+$REPO@$REF"
    ok "git $(git --version 2>/dev/null | awk '{print $3}')"
else
    case "$REPO" in
        https://github.com/*)
            SOURCE="${REPO%.git}/archive/$REF.tar.gz"
            warn "no git — installing from a source tarball instead" ;;
        *)
            die "git is not installed, and $REPO is not a GitHub URL this can
      fetch as a tarball instead.

      Debian/Ubuntu/WSL   sudo apt install git
      macOS               xcode-select --install" ;;
    esac
fi

# ── 2. an environment that belongs to yeet alone ──────────────────────────────
step "Creating an isolated environment"
if [ -d "$HOME_DIR" ]; then
    warn "replacing the existing install"
    rm -rf "$HOME_DIR"
fi
mkdir -p "$HOME_DIR"

# Resolved AFTER the venv exists, by looking — see `resolve_venv` below. It is
# `bin/python` on Unix and `Scripts/python.exe` under Git Bash, and hardcoding
# the first is why a Git Bash install got as far as step 3 and then said
# `/c/Users/.../venv/bin/python: No such file or directory`.
VENV_PY=''
VENV_BIN=''

resolve_venv() {
    if [ -x "$HOME_DIR/venv/bin/python" ]; then
        VENV_BIN="$HOME_DIR/venv/bin"
        VENV_PY="$VENV_BIN/python"
    elif [ -x "$HOME_DIR/venv/Scripts/python.exe" ]; then
        # Git Bash, MSYS2, Cygwin: a Windows venv, reached through a POSIX path.
        VENV_BIN="$HOME_DIR/venv/Scripts"
        VENV_PY="$VENV_BIN/python.exe"
    else
        die "the virtualenv has no interpreter in it.
      Looked in $HOME_DIR/venv/bin and $HOME_DIR/venv/Scripts."
    fi
}

if [ "$BACKEND" = uv ]; then
    # `>=3.10,<3.14` is a REQUEST, not a path: uv picks a satisfying
    # interpreter it can already see, and downloads a managed one when it
    # cannot. The upper bound is the point — left open, uv installs the newest
    # Python in existence, which is by definition one the CI matrix has never
    # run and the first release with no wheels for a C-extension dependency
    # would be discovered by a user rather than by us.
    #
    # It is a preference and not a requirement: a box whose only interpreter is
    # newer than the range still gets an install, with a line saying so.
    if ! spin "creating the virtualenv" 40 \
        uv venv --python ">=3.$MIN_MINOR,<3.$((MAX_TESTED + 1))" "$HOME_DIR/venv"; then
        warn "no tested Python (3.$MIN_MINOR-3.$MAX_TESTED) available — trying anything newer"
        if ! spin "creating the virtualenv" 40 \
            uv venv --python ">=3.$MIN_MINOR" "$HOME_DIR/venv"; then
            # The bar owns the last line, so anything printed straight to the
            # terminal has to retire it first or it lands on top of the bar.
            bar_clear
            sed 's/^/      /' "$HOME_DIR/install.log" >&2 2>/dev/null || true
            die "uv could not create a virtualenv.
      Re-run with YEET_NO_UV=1 to use python -m venv instead."
        fi
    fi
    resolve_venv
else
    "$PYTHON" -m venv "$HOME_DIR/venv" || die "could not create a virtualenv in $HOME_DIR"
    resolve_venv
    spin "upgrading pip" 48 "$VENV_PY" -m pip install --upgrade pip || \
        warn "could not upgrade pip; continuing with the bundled one"
fi
ok "$HOME_DIR ${MUTE}(python $("$VENV_PY" -c 'import platform; print(platform.python_version())' 2>/dev/null))${N}"

# ── 3. the tool and its dependencies ──────────────────────────────────────────
step "Installing yeet and its dependencies"
info "from $SOURCE"
INSTALL_FAILED=""
if [ "$BACKEND" = uv ]; then
    spin "resolving and downloading" 82 uv pip install --python "$VENV_PY" "$SOURCE" \
        || INSTALL_FAILED=1
else
    spin "resolving and downloading" 82 "$VENV_PY" -m pip install "$SOURCE" \
        || INSTALL_FAILED=1
fi
if [ -n "$INSTALL_FAILED" ]; then
    bar_clear
    say ""
    sed 's/^/      /' "$HOME_DIR/install.log" >&2 2>/dev/null || true
    die "the install failed. The full log is at $HOME_DIR/install.log
      Re-run with -v to watch every step instead of the progress bar."
fi

# `yeet run --tui` needs Textual, which is an OPTIONAL extra in pyproject.toml.
# Optional there is right — `pip install yeet` must not drag a display library
# into someone's tool venv — but this installer OWNS the venv it just built, so
# there is nobody else to inconvenience, and a documented flag that says
# "install another package first" is a flag that does not work.
#
# Installed as its own non-fatal step rather than as `$SOURCE[tui]`: the extras
# syntax differs between a local path, a `git+` URL and a tarball, and a
# malformed one of the three would fail the WHOLE install for the sake of a
# nicety. This way a machine with no Textual wheel still gets a working yeet,
# and `--tui` degrades to the streaming view exactly as designed.
if [ "$BACKEND" = uv ]; then
    spin "adding the dashboard" 88 uv pip install --python "$VENV_PY" 'textual>=0.80' \
        || warn "no dashboard: --tui will use the streaming view"
else
    spin "adding the dashboard" 88 "$VENV_PY" -m pip install 'textual>=0.80' \
        || warn "no dashboard: --tui will use the streaming view"
fi
# `head -1`: `yeet --version` reports the interpreter, the OS and Docker under
# the version line now, and all four inside one `ok` bullet reads as a fault.
# `$VENV_BIN`, not `venv/bin`: under Git Bash the executable is
# `venv/Scripts/yeet.exe`. `.exe` is appended only when it is there, so this
# stays one line on both.
VENV_YEET="$VENV_BIN/yeet"
[ -x "$VENV_YEET" ] || VENV_YEET="$VENV_BIN/yeet.exe"
ok "$("$VENV_YEET" --version 2>/dev/null | head -1 || echo yeet)"

# ── 4. a launcher on PATH ─────────────────────────────────────────────────────
# A tiny exec shim rather than a symlink: a symlink into the venv works, but a
# shim keeps working if ~/.local/bin is copied around, and it is obvious what
# it points at when someone cats it.
step "Putting yeet on your PATH"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/yeet" <<EOF
#!/bin/sh
# Installed by the yeet installer. Delete this file and $HOME_DIR to remove.
exec "$VENV_YEET" "\$@"
EOF
chmod 755 "$BIN_DIR/yeet"

cat > "$BIN_DIR/yeet-uninstall" <<EOF
#!/bin/sh
set -eu
printf 'Removing %s and %s\n' "$HOME_DIR" "$BIN_DIR/yeet"
rm -rf "$HOME_DIR"
rm -f "$BIN_DIR/yeet" "$BIN_DIR/yeet-uninstall"
printf 'Done.\n'
EOF
chmod 755 "$BIN_DIR/yeet-uninstall"
ok "$BIN_DIR/yeet"

# A process cannot change the environment of the shell that started it — that
# is an OS boundary, not an oversight, and it is why every curl|sh installer
# ends with either "open a new terminal" or a line to source. The profile edit
# below only reaches shells started LATER; this file is what finishes the job
# in the terminal the user is standing in right now.
#
# Written unconditionally, even when $BIN_DIR is already on PATH: it costs
# nothing, and `. ~/.local/share/yeet/env` should mean the same thing on every
# machine rather than existing only on the ones that happened to need it.
cat > "$HOME_DIR/env" <<EOF
#!/bin/sh
# Puts yeet on PATH for the current shell. SOURCE this, do not run it:
#     . "$HOME_DIR/env"
# Idempotent — sourcing it twice does not put $BIN_DIR on PATH twice.
case ":\$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) PATH="$BIN_DIR:\$PATH"; export PATH ;;
esac
EOF
chmod 644 "$HOME_DIR/env"

# fish is not POSIX and cannot source the above at all.
cat > "$HOME_DIR/env.fish" <<EOF
# Puts yeet on PATH for the current shell. SOURCE this, do not run it:
#     source $HOME_DIR/env.fish
if not contains $BIN_DIR \$PATH
    set -gx PATH $BIN_DIR \$PATH
end
EOF
chmod 644 "$HOME_DIR/env.fish"

# `~/.local/bin` is on PATH by default on many distributions and on none of the
# others. Checking is the difference between "installed" and "installed and
# usable", and it is the single most common reason a curl|sh install appears
# to have done nothing at all.
#
# TWO questions, and answering them with one variable was a bug: "is it on PATH
# in the shell that ran me" and "will it be on PATH in the next shell" have
# different answers on every re-install. The profile already holds the line, so
# the second is yes — while the first is still no, and that is exactly the run
# where the installer said nothing at all and `yeet` was not found.
case ":$PATH:" in
    *":$BIN_DIR:"*) USABLE_NOW=1 ;;
    *)              USABLE_NOW=0 ;;
esac
PATH_OK=$USABLE_NOW

if [ "$PATH_OK" = 0 ] && [ -z "${YEET_NO_MODIFY_PATH:-}" ]; then
    case "$SHELL_NAME" in
        zsh)  PROFILE="$HOME/.zshrc" ;;
        bash) if [ -f "$HOME/.bash_profile" ]; then PROFILE="$HOME/.bash_profile"; else PROFILE="$HOME/.bashrc"; fi ;;
        fish) PROFILE="$HOME/.config/fish/config.fish" ;;
        *)    PROFILE="$HOME/.profile" ;;
    esac
    LINE="export PATH=\"$BIN_DIR:\$PATH\""
    [ "$SHELL_NAME" = fish ] && LINE="fish_add_path $BIN_DIR"
    if [ -f "$PROFILE" ] && grep -Fq "$BIN_DIR" "$PROFILE" 2>/dev/null; then
        PATH_OK=1  # already there; this shell just has not re-read it
    else
        mkdir -p "$(dirname "$PROFILE")"
        printf '\n# added by the yeet installer\n%s\n' "$LINE" >> "$PROFILE"
        ok "added to PATH in ${MUTE}$PROFILE${N}"
    fi
fi

# Everything below writes whole lines and expects to own the cursor, so the bar
# is retired here rather than at the end of the script.
bar_finish

# ── optional pieces, named rather than assumed ────────────────────────────────
say ""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_NOTE="${G}${TICK}${N} Docker is running ${MUTE}— container jobs will work${N}"
elif command -v docker >/dev/null 2>&1; then
    DOCKER_NOTE="${Y}${WARN_G}${N} Docker is installed but not running"
else
    case "$(uname -s)" in
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                DOCKER_HINT="Docker Desktop + WSL integration"
            else
                DOCKER_HINT="docs.docker.com/engine/install"
            fi ;;
        Darwin) DOCKER_HINT="brew install --cask docker" ;;
        *)      DOCKER_HINT="install Docker" ;;
    esac
    DOCKER_NOTE="${Y}${WARN_G}${N} No Docker ${MUTE}— \`runs-on: local\` jobs still run ($DOCKER_HINT)${N}"
fi

# ── the panel ─────────────────────────────────────────────────────────────────
# The widths here are arithmetic, not eyeballed. Inner width W; each command row
# spends LEAD on the left gutter, CMD_W on the command, one space, and the rest
# on the description — so DESC_W is derived rather than guessed. Getting this
# wrong does not fail loudly, it just prints a box with a ragged right edge,
# which is exactly the kind of thing that makes an install feel unfinished.
W=70; LEAD=3; CMD_W=12
READY='yeet is ready.'

# Fit the terminal, or do not draw a box at all. A fixed 72-column frame wraps
# on an 80-column window with anything in the gutter and on every narrower one,
# and a wrapped box does not look like a narrow box — it looks like corruption.
[ "$((COLS - 2))" -lt "$W" ] && W=$((COLS - 2))
DESC_W=$((W - LEAD - CMD_W - 1))

if [ "$DESC_W" -lt 20 ]; then
    say ""
    printf '  %s%s%s\n\n' "$B$G" "$READY" "$N"
    printf '  %syeet scan%s    what is this project?\n' "$B" "$N"
    printf '  %syeet check%s   are the workflows correct?\n' "$B" "$N"
    printf '  %syeet run%s     run them\n' "$B" "$N"
    printf '  %syeet --help%s  every command\n' "$B" "$N"
else

printf '%s%s%s%s%s\n' "$ACCENT" "$TL" "$(rule $W)" "$TR" "$N"
printf '%s%s%s  %s%s%s%s%*s%s%s%s\n' \
    "$ACCENT" "$VT" "$N" "$B" "$G" "$READY" "$N" $((W - 2 - ${#READY})) '' "$ACCENT" "$VT" "$N"
printf '%s%s%s%*s%s%s%s\n' "$ACCENT" "$VT" "$N" $W '' "$ACCENT" "$VT" "$N"
for pair in \
    "yeet scan|what is this project, and what flows does it have?" \
    "yeet check|are the workflow files written correctly?" \
    "yeet run|run them, in Docker or your own shell" \
    "yeet --help|every command"
do
    cmd=${pair%%|*}; desc=${pair#*|}
    # Truncate rather than overflow: a description longer than the column
    # would push the right border out and undo the arithmetic above.
    desc=$(printf '%.*s' "$DESC_W" "$desc")
    printf '%s%s%s%*s%s%-*s%s %s%-*s%s%s%s%s\n' \
        "$ACCENT" "$VT" "$N" $LEAD '' \
        "$B" $CMD_W "$cmd" "$N" \
        "$MUTE" $DESC_W "$desc" "$N" "$ACCENT" "$VT" "$N"
done
printf '%s%s%s%*s%s%s%s\n' "$ACCENT" "$VT" "$N" $W '' "$ACCENT" "$VT" "$N"
printf '%s%s%s%s%s\n' "$ACCENT" "$BL" "$(rule $W)" "$BR" "$N"
fi
say ""
printf '  %s\n' "$DOCKER_NOTE"

if [ "$USABLE_NOW" = 0 ]; then
    # The last instruction of the install, so it gets the shortest thing that
    # actually works. `export PATH=...` was correct and nobody reads it as an
    # instruction — it looks like a diagnostic.
    say ""
    if [ "$SHELL_NAME" = fish ]; then
        ACTIVATE="source $HOME_DIR/env.fish"
    else
        ACTIVATE=". \"$HOME_DIR/env\""
    fi
    printf '  %s%s%s to use it in %sthis%s terminal:  %s%s%s\n' \
        "$Y" "$ARROW" "$N" "$B" "$N" "$B" "$ACTIVATE" "$N"
    printf '     %severy new terminal picks it up on its own%s\n' "$MUTE" "$N"
fi
say ""
printf '  %sremove it again with  yeet-uninstall%s\n' "$MUTE" "$N"
say ""
