# Upgrading

```console
$ yeet upgrade --check      # is there a newer one?  installs nothing
$ yeet upgrade              # get it
```

One command on every platform. It reads the latest **published** release,
downloads the wheel attached to it, and installs that into the environment yeet
already lives in. No git, no re-clone, no rebuild, and nothing else on your
machine is touched.

> **On 0.8 or earlier, `yeet upgrade` is not on your machine.** It shipped in
> 0.9, and a command cannot be back-fitted into a version already installed.
> [Re-run the installer once](#the-installer-is-always-an-upgrade-path) and you
> are current, with `yeet upgrade` available from then on.

---

## `yeet upgrade`

| | |
|---|---|
| `yeet upgrade` | install the latest published release, if it is newer |
| `yeet upgrade --check` | report only. Never installs. Cheap enough for a shell rc |
| `yeet upgrade --version v0.9` | install exactly that tag — how you pin, and how you go back |

```console
$ yeet upgrade --check
upgrading: 0.9 -> 1.0
--check: not installing. `yeet upgrade` does it, or see https://github.com/TamizhSK/YEET/releases

$ yeet upgrade
upgrading: 0.9 -> 1.0
yeet 1.0 installed. `yeet --version` to confirm.
```

Already current, it says so and stops:

```console
$ yeet upgrade
yeet 1.0 is the latest.
```

**It installs the wheel, not a git ref.** `pip install git+https://…` needs git,
needs a full clone and builds from source. The release already carries
`yeet-<version>-py3-none-any.whl`, and CI gates every release on the tag
matching the built version — so this installs exactly the artifact that was
tested, on a machine that may have no git at all.

**Drafts are invisible to it.** An unpublished release is not shipped, and
`yeet upgrade` will never hand you a build its author has not published.

### On a development checkout

```console
$ yeet upgrade
[!] this is a development checkout at /home/you/src/YEET
    `git pull` updates it. Upgrading would replace your working tree with a
    published wheel.
```

It refuses rather than overwriting your source with a release. `git pull` is
what you wanted.

### Going back

```console
$ yeet upgrade --version v0.9
```

Any published tag works, including older ones. One warning to expect:

```console
$ yeet upgrade --version v0.6
installing: 1.0 -> 0.6
[!] v0.6 predates `yeet upgrade` — it will not be there afterwards.
    To come back, re-run the installer for your platform.
```

That is a **one-way door**. Releases before 0.9 have no `yeet upgrade` in them,
so the way back up is the install one-liner, not the command you just used.

### Rate limits

`yeet upgrade` asks the GitHub API which release is current. Unauthenticated
calls are capped at **60 per hour per IP** — shared office addresses and CI
runners burn through that without anyone doing anything wrong. yeet passes a
token when it can find one (`gh auth login`, `$GITHUB_TOKEN`, or your git
credential helper — the same lookup [`secrets.md`](secrets.md) describes), which
lifts the cap to 5000/hour. Nothing to configure if you already have one.

---

## The installer is always an upgrade path

Re-running the one-liner for your platform replaces the install in place. It is
the **only** path from 0.8 or earlier, and it stays supported forever.

**Linux, macOS, WSL, Git Bash**

```bash
curl -fsSL https://raw.githubusercontent.com/TamizhSK/YEET/main/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex
```

It reads the outgoing version before it removes anything, so you can see that it
moved:

```
[2/4] Creating an isolated environment
      !   replacing yeet 0.8
...
[3/4] Installing yeet and its dependencies
      ok  yeet 1.0
      ok  upgraded 0.8 -> 1.0
```

and when it did not:

```
      !   replacing yeet 1.0
      ok  yeet 1.0
          already on 1.0 — reinstalled
```

Your PATH entries, shell profile lines and Windows registry PATH are idempotent
— re-running adds nothing a second time.

**What is NOT touched:** every project's `.yeet/` directory. Flows, the
encrypted secret store, run logs and caches all live in the project, not in the
install, so upgrading cannot disturb them.

### Pinning a version at install time

```bash
curl -fsSL .../install.sh | sh -s -- --version v0.9
```

On PowerShell the piped form takes no parameters — `irm | iex` has nowhere to
put them — so pin with the environment variable, or download the script and use
the flag:

```powershell
$env:YEET_REF = 'v0.9'; irm .../install.ps1 | iex
.\install.ps1 -Version v0.9        # if you saved it first
```

`YEET_REF` works for `install.sh` too, which is what a Dockerfile or a
provisioning script usually wants.

---

## If you installed another way

The installers are one route, not the only one. Use whatever you installed with:

| Installed with | Upgrade with |
|---|---|
| `install.sh` / `install.ps1` | `yeet upgrade`, or re-run the one-liner |
| `pipx install git+https://github.com/TamizhSK/YEET` | `pipx upgrade yeet` |
| `uv tool install git+https://github.com/TamizhSK/YEET` | `uv tool upgrade yeet` |
| `pip install` into your own venv | `pip install --upgrade <wheel URL from the releases page>` |
| a git clone | `git pull` |

`yeet upgrade` installs into whichever environment it is running from, so it
works inside a pipx or uv venv too — but that tool's own command is the one that
keeps its metadata straight, so prefer it where you have it.

---

## In CI

**Pin.** A workflow that installs `main` is a workflow whose behaviour changes
without a commit:

```yaml
- run: curl -fsSL https://raw.githubusercontent.com/TamizhSK/YEET/main/install.sh | sh -s -- --version v1.0
```

Or install the wheel directly, which needs no git and no clone:

```yaml
- run: pip install https://github.com/TamizhSK/YEET/releases/download/v1.0/yeet-1.0-py3-none-any.whl
```

Never `yeet upgrade` in CI — it makes the run depend on what was published that
morning, which is the thing pinning exists to prevent.

---

## Which version am I on?

```console
$ yeet --version
yeet 1.0
python 3.12.3 (/home/you/.local/share/yeet/venv/bin/python)
os     Linux 6.8.0 (X64)
docker 27.3.1

$ yeet doctor        # the same, plus everything a run needs
```

Every release, its notes and its artifacts:
<https://github.com/TamizhSK/YEET/releases>

---

## Related

* [`secrets.md`](secrets.md) — where secrets live, and why upgrading never
  touches them.
* [`docker.md`](docker.md) — the daemon, per OS.
* [`writing-flows.md`](writing-flows.md) — every command and flag.
