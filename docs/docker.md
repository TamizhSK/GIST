# Docker, on every OS

`yeet run` puts each job in a container, so it needs a daemon it can reach.
This page is what to do when it says it cannot — and what yeet now does about
it before bothering you.

Start here, always:

```console
$ yeet doctor
  ok   docker            daemon 27.3.1 (linux/arm64)
  ...  docker host       unix:///Users/you/.colima/default/docker.sock
```

`yeet doctor` reports the endpoint it actually connected to. If that line is a
surprise, it is the answer.

---

## "no Docker daemon is listening" while `docker ps` works

This used to be the most confusing failure the tool could produce, because the
evidence in front of you contradicts it. It has a real cause.

`docker.from_env()` — the Python SDK — reads `$DOCKER_HOST` **and nothing
else**. The `docker` CLI reads `docker context`, which is a JSON file under
`~/.docker/contexts/` that no environment variable mentions. Colima, Rancher
Desktop, Podman, Lima and rootless dockerd all install themselves by creating a
context and never exporting `DOCKER_HOST`. On those machines the CLI finds the
daemon and the SDK does not.

**yeet now reads the same context file the CLI does**, and then falls back
through every well-known socket, before it will tell you nothing is listening:

| | tried, in order |
|---|---|
| all | the active `docker context` (`$DOCKER_CONTEXT`, else `currentContext` in `~/.docker/config.json`) |
| macOS / Linux / WSL | `/var/run/docker.sock` · `~/.docker/run/docker.sock` (Docker Desktop) · `~/.colima/default/docker.sock` · `~/.rd/docker.sock` (Rancher) · `~/.lima/docker/sock/docker.sock` · Podman's machine socket · `$XDG_RUNTIME_DIR/docker.sock` (rootless) · `$XDG_RUNTIME_DIR/podman/podman.sock` |
| Windows | `npipe:////./pipe/dockerDesktopLinuxEngine` · `npipe:////./pipe/docker_engine` |

Whichever answers is exported as `$DOCKER_HOST` for the rest of the run, so the
places yeet shells out to the `docker` **binary** land on the same daemon.

If you would rather be explicit, set it yourself and nothing above runs:

```console
$ export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock   # macOS / Linux
> $env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine' # PowerShell
```

---

## The message, per platform

The run stops with **exit code 3** — distinct from 1 ("your workflow failed") on
purpose, so a script can tell "this machine cannot run containers" from "the
build is broken".

### Windows

```
no Docker daemon is listening
Is Docker Desktop running? Start it and try again.
```

A stopped Docker Desktop reports itself as `open
//./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified` —
no "connection refused", no "no such file or directory". Those Win32 phrasings
are now translated rather than printed raw, so the most common Docker failure on
the most common desktop OS reads like a sentence.

If Docker Desktop *is* running and you still see this, it is usually still
starting: the pipe appears before the engine answers on it. yeet says "the
Docker daemon did not answer in time (still starting up?)" for that case.

### WSL

```
no Docker daemon is listening
Enable WSL integration: Docker Desktop -> Settings -> Resources -> WSL Integration,
then tick this distro.
```

The daemon runs on the Windows side; a distro without integration ticked has no
socket at all. This is a checkbox, not an install.

### macOS

```
no Docker daemon is listening
Is Docker Desktop running? Start it and try again.
```

With Colima or Rancher Desktop instead, `colima start` / opening Rancher is the
fix — and the context lookup above means you do not have to set `DOCKER_HOST`.

### Linux

```
no Docker daemon is listening
Start the daemon: `sudo systemctl start docker` (or `sudo service docker start`).
```

And its close relative, which is a **different problem**:

```
the Docker socket exists but this user cannot open it
```

The daemon is up; your user is not in the `docker` group.

```console
$ sudo usermod -aG docker $USER   # then log out and back in
```

---

## When it fails

**Once, and before the run starts.** yeet reaches the daemon up front rather
than from inside the thread pool, so a five-job workflow prints one error
instead of five, and prints it before the live run tree has taken over the
terminal.

Skipped when a job's `runs-on` is still an expression (`${{ matrix.os }}`) —
that workflow may turn out to be entirely `cooked_on: local`, and refusing to
start it over a daemon it will never touch would be wrong.

**A job that asked for the host never needs any of this.** `cooked_on: local`
runs in your own shell, and a workflow where every job says so never touches the
SDK at all.

---

## The daemon dying mid-run

Docker Desktop restarting for an update, `docker kill` from another shell, the
OOM killer. A container that dies under a running step surfaces as a truncated
stream and exit code 137, which on its own reads as "your build failed". It did
not; it never finished. yeet asks the daemon which it was:

```
the container ran out of memory and was killed (raise Docker's memory limit)
the container stopped while this step was running (exit 137) — was it `docker kill`ed,
  or did Docker restart?
YEET-E321: the Docker daemon went away while starting the job
```

---

## Leftovers

A machine that loses power mid-`npm ci` leaves a stopped container holding its
name, and the next run of that job cannot start ("name already in use").

```console
$ yeet prune            # this project's leftover containers
$ yeet prune --actions  # the fetched-action cache too
```

Containers are labelled with the project, run and job, so `yeet prune` only ever
touches this project — never a colleague's run in another checkout.

---

## Related

* [`secrets.md`](secrets.md) — including why a container has none of your git
  credentials, and what yeet passes in.
* [`writing-flows.md`](writing-flows.md) — `cooked_on: local` and every other
  flag.
* [`rules.md`](rules.md) — E315 (unknown runner label), E321 (the daemon
  refused).
