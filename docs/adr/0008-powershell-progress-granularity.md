# 0008 — The PowerShell bar moves in steps, not smoothly

**Status:** accepted
**Date:** 2026-08-18

## Context

`install.sh` animates its progress bar: the work runs in the background, the
shell polls with `kill -0`, and the bar creeps toward the step's target while
`pip` downloads. `install.ps1` does not. Its bar jumps twice per long
operation — once to the halfway point before the call, once to the target
after it — and stands still in between.

The asymmetry is deliberate and it is worth writing down, because the fix looks
obvious and is not.

Animating it means polling, and polling a native command in PowerShell means
giving up this:

```powershell
& $Exe @Arguments *> $log
```

The call operator with a **splatted array** is what keeps each argument intact
through the shell. Replacing it with `Start-Process`, `Start-Job`, or a
`System.Diagnostics.ProcessStartInfo` means re-quoting the argument list by
hand, into a single command line, with Windows' own quoting rules.

`C:\Users\Tamizh Selvan\AppData\Local\yeet` is the standard way that breaks —
a real path, from a real contributor's machine, with a space in it. An
installer that puts the venv in `C:\Users\Tamizh` is not a cosmetic failure.

## Decision

Keep the synchronous splatted call. Move the bar to the halfway point before a
long operation and to its target after, and accept that it does not move during
the operation itself.

The label on the bar line carries the information the movement would have:
`resolving and downloading` at 63% says which step is slow, which is what
someone reports when an install hangs. Motion would only have said "still
alive".

## Consequences

- A `pip install` over a slow link shows a stationary bar for up to a minute.
  The label says what it is doing; `-Verbose` is not wired up on the Windows
  side, and the log is at `%LOCALAPPDATA%\yeet\install.log`.
- The two installers are visibly different at that moment. That is the cost.
- **Do not "fix" this by switching to `Start-Process` without solving the
  quoting first.** If someone wants smooth motion, the correct route is a
  runspace or a background job that still receives an argument *array* —
  `Start-Job -ScriptBlock { & $using:Exe @using:Arguments }` is worth trying,
  and worth testing against a path with a space in it before it lands.
- The POSIX side keeps its animation because `sh` can background a job and poll
  it without touching how the arguments were parsed.
