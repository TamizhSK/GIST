#!/bin/sh
# yeet installer — Linux, macOS, and WSL.
#
#   curl -fsSL https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh | sh
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
# Environment:
#   YEET_REPO      git URL to install from      (default: the GitHub repo)
#   YEET_REF       branch, tag or commit        (default: main)
#   YEET_HOME      where the venv lives         (default: ~/.local/share/yeet)
#   YEET_BIN_DIR   where the launcher goes      (default: ~/.local/bin)
#   YEET_NO_MODIFY_PATH=1   don't offer to edit your shell profile

set -eu

REPO="${YEET_REPO:-https://github.com/TamizhSK/GIST}"
REF="${YEET_REF:-main}"
HOME_DIR="${YEET_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/yeet}"
BIN_DIR="${YEET_BIN_DIR:-$HOME/.local/bin}"
MIN_MINOR=10
TOTAL_STEPS=4

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

if [ "$UNICODE" = 1 ]; then
    TL='╭'; TR='╮'; BL='╰'; BR='╯'; HZ='─'; VT='│'
    TICK='✔'; CROSS='✘'; WARN_G='▲'; ARROW='→'; DOT='●'
else
    TL='+'; TR='+'; BL='+'; BR='+'; HZ='-'; VT='|'
    TICK='ok'; CROSS='xx'; WARN_G='!'; ARROW='->'; DOT='*'
fi

say()  { printf '%s\n' "$*"; }
rule() { i=0; s=''; while [ "$i" -lt "$1" ]; do s="$s$HZ"; i=$((i + 1)); done; printf '%s' "$s"; }

banner() {
    [ "$TTY" = 0 ] && { say "yeet installer"; say ""; return; }
    say ""
    printf '%s%s   ▄  ▄  ▄▄▄  ▄▄▄  ▄▄▄%s\n' "$B" "$ACCENT" "$N"
    printf '%s%s   ▀▄▀  ██▄  ██▄   ▐█ %s   %sa local GitHub Actions runner%s\n' "$B" "$ACCENT" "$N" "$MUTE" "$N"
    printf '%s%s    █   ▄▄█  ▄▄█   ▐█ %s   %swith a dialect of its own%s\n' "$B" "$ACCENT" "$N" "$MUTE" "$N"
    say ""
}

# A step counter rather than a bare bullet: on a slow network the pip step can
# sit for a minute, and "3/4" is the difference between waiting and wondering.
STEP_NO=0
step() {
    STEP_NO=$((STEP_NO + 1))
    printf '%s%s[%s/%s]%s %s%s%s\n' "$B" "$ACCENT" "$STEP_NO" "$TOTAL_STEPS" "$N" "$B" "$*" "$N"
}
ok()    { printf '      %s%s%s %s\n' "$G" "$TICK" "$N" "$*"; }
info()  { printf '      %s%s%s\n' "$MUTE" "$*" "$N"; }
warn()  { printf '      %s%s%s %s\n' "$Y" "$WARN_G" "$N" "$*"; }
die()   { printf '\n  %s%s %s%s\n\n' "$R" "$CROSS" "$*" "$N" >&2; exit 1; }

# Runs a command with a spinner, keeping its output for the failure path only.
# The success path stays quiet on purpose: pip's resolver output is 40 lines of
# noise nobody reads, right up until it fails and every one of them matters.
spin() {
    _label="$1"; shift
    if [ "$TTY" = 0 ]; then
        info "$_label..."
        "$@" >"$HOME_DIR/install.log" 2>&1 || return 1
        return 0
    fi
    "$@" >"$HOME_DIR/install.log" 2>&1 &
    _pid=$!
    _frames='- \ | /'
    while kill -0 "$_pid" 2>/dev/null; do
        for _f in $_frames; do
            printf '\r      %s%s%s %s ' "$ACCENT" "$_f" "$N" "$_label"
            sleep 0.1
            kill -0 "$_pid" 2>/dev/null || break
        done
    done
    wait "$_pid" || { printf '\r%*s\r' 70 ''; return 1; }
    printf '\r%*s\r' 70 ''
    return 0
}

banner

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

command -v git >/dev/null 2>&1 || die "git is required to install from the repo.

      Debian/Ubuntu/WSL   sudo apt install git
      macOS               xcode-select --install"
ok "git $(git --version 2>/dev/null | awk '{print $3}')"

# ── 2. an environment that belongs to yeet alone ──────────────────────────────
step "Creating an isolated environment"
if [ -d "$HOME_DIR" ]; then
    warn "replacing the existing install"
    rm -rf "$HOME_DIR"
fi
mkdir -p "$HOME_DIR"

VENV_PY="$HOME_DIR/venv/bin/python"
if [ "$BACKEND" = uv ]; then
    # `>=3.10` is a REQUEST, not a path: uv picks a satisfying interpreter it
    # can already see, and downloads a managed one when it cannot.
    if ! spin "creating the virtualenv" uv venv --python ">=3.$MIN_MINOR" "$HOME_DIR/venv"; then
        sed 's/^/      /' "$HOME_DIR/install.log" >&2 2>/dev/null || true
        die "uv could not create a virtualenv.
      Re-run with YEET_NO_UV=1 to use python -m venv instead."
    fi
else
    "$PYTHON" -m venv "$HOME_DIR/venv" || die "could not create a virtualenv in $HOME_DIR"
    spin "upgrading pip" "$VENV_PY" -m pip install --upgrade pip || \
        warn "could not upgrade pip; continuing with the bundled one"
fi
ok "$HOME_DIR ${MUTE}(python $("$VENV_PY" -c 'import platform; print(platform.python_version())' 2>/dev/null))${N}"

# ── 3. the tool and its dependencies ──────────────────────────────────────────
step "Installing yeet and its dependencies"
info "from $REPO@$REF"
INSTALL_FAILED=""
if [ "$BACKEND" = uv ]; then
    spin "resolving and downloading" uv pip install --python "$VENV_PY" "git+$REPO@$REF" \
        || INSTALL_FAILED=1
else
    spin "resolving and downloading" "$VENV_PY" -m pip install "git+$REPO@$REF" \
        || INSTALL_FAILED=1
fi
if [ -n "$INSTALL_FAILED" ]; then
    say ""
    sed 's/^/      /' "$HOME_DIR/install.log" >&2 2>/dev/null || true
    die "the install failed. The full log is at $HOME_DIR/install.log"
fi
ok "$("$HOME_DIR/venv/bin/yeet" --version 2>/dev/null || echo yeet)"

# ── 4. a launcher on PATH ─────────────────────────────────────────────────────
# A tiny exec shim rather than a symlink: a symlink into the venv works, but a
# shim keeps working if ~/.local/bin is copied around, and it is obvious what
# it points at when someone cats it.
step "Putting yeet on your PATH"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/yeet" <<EOF
#!/bin/sh
# Installed by the yeet installer. Delete this file and $HOME_DIR to remove.
exec "$HOME_DIR/venv/bin/yeet" "\$@"
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

# `~/.local/bin` is on PATH by default on many distributions and on none of the
# others. Checking is the difference between "installed" and "installed and
# usable", and it is the single most common reason a curl|sh install appears
# to have done nothing at all.
case ":$PATH:" in
    *":$BIN_DIR:"*) PATH_OK=1 ;;
    *)              PATH_OK=0 ;;
esac

if [ "$PATH_OK" = 0 ] && [ -z "${YEET_NO_MODIFY_PATH:-}" ]; then
    case "${SHELL##*/}" in
        zsh)  PROFILE="$HOME/.zshrc" ;;
        bash) if [ -f "$HOME/.bash_profile" ]; then PROFILE="$HOME/.bash_profile"; else PROFILE="$HOME/.bashrc"; fi ;;
        fish) PROFILE="$HOME/.config/fish/config.fish" ;;
        *)    PROFILE="$HOME/.profile" ;;
    esac
    LINE="export PATH=\"$BIN_DIR:\$PATH\""
    [ "${SHELL##*/}" = fish ] && LINE="fish_add_path $BIN_DIR"
    if [ -f "$PROFILE" ] && grep -Fq "$BIN_DIR" "$PROFILE" 2>/dev/null; then
        PATH_OK=1  # already there; this shell just has not re-read it
    else
        mkdir -p "$(dirname "$PROFILE")"
        printf '\n# added by the yeet installer\n%s\n' "$LINE" >> "$PROFILE"
        ok "added to PATH in ${MUTE}$PROFILE${N}"
    fi
fi

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
COLS=$( (tput cols) 2>/dev/null || echo "${COLUMNS:-80}" )
case "$COLS" in ''|*[!0-9]*) COLS=80 ;; esac
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

if [ "$PATH_OK" = 0 ]; then
    say ""
    printf '  %s%s%s open a new terminal, or run:  %sexport PATH="%s:$PATH"%s\n' \
        "$Y" "$ARROW" "$N" "$B" "$BIN_DIR" "$N"
fi
say ""
printf '  %sremove it again with  yeet-uninstall%s\n' "$MUTE" "$N"
say ""
