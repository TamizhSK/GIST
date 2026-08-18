# YEET audits

The launch readiness audit lives in [`docs/audit/report.md`](docs/audit/report.md).
Follow-ups are appended here.

---

## Follow-up: install TUI, encoding, rename — 2026-08-18

Audited from macOS 15 (Apple Silicon), Docker 29.6.2, PowerShell 7.5 in a Linux
container, no Windows machine. Everything marked verified was **run**.

### Verdict

The POSIX path is verified; the Windows path is argued. Every claim about
`install.sh` here was executed under a real pty at seven widths and is now held
by twenty-two tests that fail when the behaviour is mutated. Nothing about
`install.ps1` has been executed on Windows by anyone — it parses, PSScriptAnalyzer
is clean, and its drawing functions were run in isolation under PowerShell 7 on
Linux, which is not the same thing as a PowerShell 5.1 console with a raster
font. The single highest-value finding is that **the UTF-8 switch was solving
the wrong problem**: a stock CP437 console round-trips `█` and `░` correctly and
never needed it, while CP1252 mangles both to `¦` — so keying the fallback on
`CodePage -eq 65001` printed the ASCII wordmark to precisely the machines that
could have rendered the real one. That is fixed and is a strictly better outcome
than making the switch work. What remains open is the font, which no API exposes
and no probe can reach; the answer there is an explicit `--ascii` override plus
[`docs/VERIFY-WINDOWS.md`](docs/VERIFY-WINDOWS.md), which nobody has run yet.

### P0

| # | Finding | Evidence | Fix | Est |
|---|---|---|---|---|
| W1 | **BOM trap not present.** `install.ps1:95` assigns `New-Object System.Text.UTF8Encoding $false`, not `[System.Text.Encoding]::UTF8` | Ran both in PowerShell: `GetPreamble().Length` is 0 for ours, 3 for the trap | none needed | — |
| W2.2 | **Codepage was the wrong signal.** CP437 encodes `█`→`0xDB`, `░`→`0xB0` and round-trips both; CP1252 sends both to `0xA6`. The old check declared 437 incapable | `[Text.Encoding]::GetEncoding(437)` round-trip, run in the PS container | `Test-BlockGlyphs` round-trips the two characters through the live encoding; UTF-8 is requested only when that fails, and re-probed after | done |
| W2.1 | **Font is undetectable and defeats every probe.** A raster-font console shows boxes at any codepage | reasoning; no Windows box here | `-Ascii` / `$env:YEET_ASCII`, and `--ascii` / `YEET_ASCII` on POSIX | done |
| W2.3 | Override existed nowhere and was documented nowhere | — | flag + env var in both installers, documented in README and `--help` | done |
| — | **Windows rendering unverified end to end** | — | [`docs/VERIFY-WINDOWS.md`](docs/VERIFY-WINDOWS.md), 8 steps, ~20 min, needs a human | **open** |

### P1

| # | Finding | Evidence | Fix | Est |
|---|---|---|---|---|
| W1.2 | Restore is not in a `finally`. Normal exit, `Stop-Install` and a `trap` all restore; **Ctrl-C does not** | read | `trap { Restore-Console; break }` added, covering terminating errors. `finally` needs the whole 300-line body re-indented in a file nobody here can execute — recorded as a known gap in VERIFY-WINDOWS step 4 rather than done blind | partial |
| W1.3 | `$OutputEncoding` (what PowerShell pipes *to* native commands) vs `[Console]::OutputEncoding` (what the console renders) | — | Only `[Console]::OutputEncoding` is touched, which is the one that governs rendering. `$OutputEncoding` is deliberately untouched: nothing here pipes text *into* a native command | done |
| W4.1 | Bar showed a percentage and no label — "stuck at 63%" is not a report | — | fixed-width label field on the bar line, dropped below 60 columns rather than squeezed | done |
| W4.2 | No way to get the transcript back on a terminal | — | `-v` / `--verbose`, and the failure path now names it | done |
| W4.3 | Ctrl-C left a half-painted bar and no cursor restore | — | `trap on_interrupt INT TERM` — clears the bar, `tput cnorm`, exits 130 | done |
| W4.4 | Warning printed during a bar could be overwritten by the next frame | now asserted by test | already correct (`bar_clear` → print → redraw); test added that fails when `bar_clear` is removed | done |
| W5.1 | `stty size <&2` is defeated by `2>log` | — | four rungs: `<&2` → `</dev/tty` → `$COLUMNS` → 80 | done |
| W5.2 | `$COLS` measured once; a resize was ignored for the whole run | — | re-measured every 10th frame (~1s). Per-frame is a process 10×/second; never is wrong | done |
| W5.3 | 40 columns untested | now a test parameter | label dropped, bar still fills; verified at 110/100/80/72/64/46/40 | done |
| W6 | The pty-capture lesson lived in a chat log | — | `tests/support/pty_capture.py` + `tests/unit/test_install_bar.py` (22 tests, 3s) | done |
| W3.1 | Renaming away from `GIST` does not reserve it | — | **not done** — creating a public repo in someone's namespace is theirs to do; command below | **open** |
| W3.5 | Transcripts kept old URLs with no note | — | header added to `DEV-A.md` / `DEV-B.md` | done |
| W3.4 | Local remote still pointed at the old name | `git remote -v` | `set-url` to `TamizhSK/YEET` | done |

### P2

| # | Finding | Evidence | Fix | Est |
|---|---|---|---|---|
| W7 | PowerShell bar granularity was decided, not recorded | — | [`docs/adr/0008-powershell-progress-granularity.md`](docs/adr/0008-powershell-progress-granularity.md) | done |
| W3.6 | No install-script checksum has ever been published | `grep` for sha256 across the repo and README: none | nothing to correct | done |

### Corrections to the brief

- **W2.2**: `░` (U+2591) maps to **`0xB0`** in CP437, not `0xB1`. `0xB0` is the
  light shade; `0xB1` is medium. Verified by round-trip.
- **W3.3**: `raw.githubusercontent.com` **does** serve the old name — it returns
  `200` directly, not a redirect, while `github.com/TamizhSK/GIST` returns `301`.
  Anyone holding the old one-liner is fine, so there is nothing for release notes.
  (My own earlier check of this used `curl -L`, which cannot tell `200` from
  `301`→`200`; this one does not follow redirects.)
- **W3.2**: agreed and worth stating precisely — only the account owner can
  create a repo in their own namespace, so the near risk is self-inflicted. The
  real exposure is account deletion or a username change, after which the whole
  namespace is claimable by anyone, and nothing in this repo can mitigate that.

### Still unverified, and by whom

| What | Why it cannot be settled here | Who | Machine |
|---|---|---|---|
| Wordmark renders on stock PS 5.1 | No Windows host; the font question has no API | **needs an owner** | any Windows box, default console host |
| Whether CP437 alone now suffices (no UTF-8 switch) | Same | **needs an owner** | same, note codepage before/after |
| `-Ascii` works on a console that defeats the blocks | Same | **needs an owner** | same |
| Encoding restored after Ctrl-C | Known gap — restore is not in a `finally` | **needs an owner** | same |
| No BOM above the wordmark | Preamble proven 0 bytes; the *rendering* is not | **needs an owner** | same |
| Git Bash install | CI covers `installer-gitbash`, but not the drawing | **needs an owner** | same |
| `GIST` namespace reserved | Creating a repo in another person's account | **TamizhSK** | `gh repo create TamizhSK/GIST --public -d "Renamed to YEET"` |

Everything else in this follow-up was executed on this machine: seven terminal
widths under a pty, two deliberate mutations to prove the tests bite, CP437 /
CP1252 / CP65001 round-trips, both raw URLs without redirect-following, and
`install.sh` end to end on macOS, ubuntu:22.04 and alpine:3.20.
