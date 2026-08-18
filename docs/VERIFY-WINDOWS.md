# Verifying the Windows installer on a real machine

**Status: NOT YET RUN. Until someone completes this and pastes results into the
PR, the Windows rendering path is argued, not verified.**

About twenty minutes. You need a Windows box; nothing else here can be done
from macOS or Linux, which is the whole reason this file exists.

## What is actually in question

The installer draws a wordmark and a progress bar out of `█` (U+2588) and
`░` (U+2591). Two separate things have to be true for those to appear:

1. **The encoding** must be able to carry the characters. This the script can
   test, and does — it round-trips both characters through the active console
   encoding before deciding. Confirmed from .NET on Linux:

   | Codepage | `█` | `░` | usable |
   |---|---|---|---|
   | 437 (stock console) | `0xDB` | `0xB0` | yes |
   | 1252 | `0xA6` | `0xA6` | no — both become `¦` |
   | 65001 | UTF-8 | UTF-8 | yes |

2. **The font** must have a glyph for them. This the script **cannot** test.
   No Windows API reports the console font in a way a script can act on, and a
   console set to the raster **Terminal** font shows a box or a blank at any
   codepage. This is the gap these steps exist to measure.

`-Ascii` / `$env:YEET_ASCII=1` forces the `#` wordmark and bar, and is the
stated way out for anyone whose console defeats both.

## Before you start

```powershell
# Record the starting state — step 4 checks it was put back.
[Console]::OutputEncoding.CodePage
$PSVersionTable.PSVersion
```

Write both down.

## 1 — Stock `powershell.exe` 5.1, default font

Open **Windows PowerShell** from the Start menu. Do not use Windows Terminal
for this one; the point is the default console host.

```powershell
Get-ItemProperty HKCU:\Console | Select-Object FaceName, FontFamily
[Console]::OutputEncoding.CodePage
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex"
```

**Record:** the reported `FaceName`, the codepage before, and a screenshot of
the first ten lines.

| What you see | Means |
|---|---|
| Solid block wordmark and a gradient bar | Working. Note whether the codepage was 437 already. |
| `#` wordmark | The probe said no. Record the codepage — this is the case worth understanding. |
| Boxes, `?`, or `¦¦¦` | **The bug.** Encoding said yes, the font said no. Capture it and go to step 3. |

## 2 — The same console, Consolas

Right-click the title bar → Properties → Font → **Consolas** → OK. Then re-run
the same command.

If step 1 showed boxes and this shows blocks, the fallback is keyed on the
wrong signal and needs a documented escape rather than a smarter probe — which
is exactly what `-Ascii` is.

## 3 — The explicit override

```powershell
$env:YEET_ASCII = 1
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex"
Remove-Item Env:\YEET_ASCII
```

**Expected:** `#` wordmark, `#` bar, install completes. This must work on every
console; it is the guaranteed path.

## 4 — The encoding is handed back

Immediately after any of the runs above:

```powershell
[Console]::OutputEncoding.CodePage
```

**Expected:** the number you wrote down at the start.

If it says `65001` and you started at `437`, the restore did not run — say
which run it followed. Known gap: `Ctrl-C` part-way through is **not** covered
(the restore is on the normal exit, on `Stop-Install`, and in a `trap`, but not
in a `finally`), so test that separately and expect it to fail:

```powershell
# Start it, press Ctrl-C during step 3, then:
[Console]::OutputEncoding.CodePage
```

## 5 — No BOM

The failure mode is `ï»¿` printed before the wordmark, from assigning
`[System.Text.Encoding]::UTF8` (which carries a 3-byte preamble) instead of
`[System.Text.UTF8Encoding]::new($false)`. The script uses the second.

**Expected:** no stray characters above the wordmark. Confirm from the
screenshot in step 1.

## 6 — PowerShell 7 in Windows Terminal

```powershell
pwsh -Command "irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex"
```

**Expected:** blocks and gradient, no encoding switch needed (already 65001).

## 7 — Git Bash

```bash
curl -fsSL https://raw.githubusercontent.com/TamizhSK/YEET/main/install.sh | sh
~/.local/bin/yeet --version
```

**Expected:** installs, and `yeet --version` prints. This path finds the venv
at `venv/Scripts/python.exe` rather than `venv/bin/python`.

## 8 — Resize mid-install

Start an install and drag the window narrower while the bar is moving.

**Expected:** the bar re-fits within about a second. `install.sh` re-measures
every tenth frame; `install.ps1` asks `$Host.UI.RawUI` on every draw.

## Paste this into the PR

```
Machine:            Windows __ , PowerShell __
Console font:       ____________
Codepage before:    ____   after: ____

1 stock 5.1 default font    blocks / hashes / boxes     screenshot: [ ]
2 same + Consolas           blocks / hashes / boxes
3 YEET_ASCII=1              hashes, install completed:  yes / no
4 encoding restored         yes / no      after Ctrl-C: yes / no
5 no BOM above wordmark     yes / no
6 pwsh 7 + Terminal         blocks / hashes / boxes
7 Git Bash install          yes / no
8 resize re-fits            yes / no
```
