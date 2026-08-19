<#
.SYNOPSIS
  yeet installer for Windows.

.DESCRIPTION
  irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex

  Does what install.sh does, in the same order and with the same layout on
  disk: finds a Python 3.10+, builds a virtualenv that belongs to yeet alone,
  installs yeet into it, and drops a launcher on PATH. It never installs into
  your system Python, never touches a project's virtualenv, and never needs an
  elevated prompt.

  Windows PowerShell 5.1 AND PowerShell 7. That constraint is why this file has
  no `??`, no ternary, and no `-AsByteStream` — 5.1 is still the default on a
  stock Windows 11 box, and a script that only runs in 7 does not run for the
  people most likely to paste it.

.PARAMETER Version
  A tag, branch or commit. Default: main.

.PARAMETER Local
  Install from the clone this script sits in — already the default when it sits
  in one, so this only says out loud what would have happened anyway.

.PARAMETER System
  Also add the launcher to the MACHINE PATH, so every account on this box can
  run `yeet`. Needs an elevated prompt, and is additive — the user PATH is set
  either way. `$env:YEET_SYSTEM_PATH=1` does the same, which is what `irm | iex`
  needs, since that form cannot take arguments.

.PARAMETER Ascii
  Draw the wordmark and the bar with `#` instead of block characters. Whether a
  console can RENDER U+2588 depends on its font, and a font is not something a
  process can ask about — a raster "Terminal" font shows a box no matter what
  the codepage says. This is the stated way out for anyone whose console
  defeats the automatic path. `$env:YEET_ASCII=1` does the same, which is what
  `irm | iex` needs, since that form cannot take arguments.

.EXAMPLE
  irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex

.EXAMPLE
  # Pinning a version needs the script on disk — `iex` cannot take arguments.
  irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 -OutFile i.ps1
  .\i.ps1 -Version v0.7

.NOTES
  Under a Restricted execution policy `irm | iex` is refused. That is the
  policy working, and the way past it for one command is:
      powershell -ExecutionPolicy Bypass -Command "irm <url> | iex"
#>

[CmdletBinding()]
param(
    [string]$Version = $(if ($env:YEET_REF) { $env:YEET_REF } else { 'main' }),
    [switch]$Local,
    [switch]$System,
    [switch]$Ascii
)

$ErrorActionPreference = 'Stop'

$Repo = if ($env:YEET_REPO) { $env:YEET_REPO } else { 'https://github.com/TamizhSK/YEET' }
# %LOCALAPPDATA%, not Program Files: no elevation, and it is per-user, which is
# what an isolated application install should be.
$HomeDir = if ($env:YEET_HOME) { $env:YEET_HOME } else { Join-Path $env:LOCALAPPDATA 'yeet' }
$BinDir = if ($env:YEET_BIN_DIR) { $env:YEET_BIN_DIR } else { Join-Path $HomeDir 'bin' }
$MinMinor = 10
$MaxTested = 13
$TotalSteps = 4
# `-System` OR the environment variable, because `irm | iex` cannot pass a
# switch. Read once, here, so the PATH step has one thing to test.
$WantSystemPath = ($System -or $env:YEET_SYSTEM_PATH)

# --- presentation ------------------------------------------------------------
# Same two independent questions install.sh asks. `$Host.UI.RawUI` is absent
# when the output is redirected or the host is not a console, and NO_COLOR is
# honoured because it is honoured everywhere else in this project.

$script:Tty = $false
try {
    $script:Tty = (-not [Console]::IsOutputRedirected) -and (-not $env:NO_COLOR)
} catch {
    $script:Tty = $false
}

# CAN THIS CONSOLE CARRY THE BLOCK CHARACTERS? Asked by round-tripping them
# through the active encoding, not by comparing the codepage to 65001 — and the
# difference is not academic:
#
#   CP437  (the stock console)  U+2588 -> 0xDB, U+2591 -> 0xB0, both round-trip
#   CP1252                      both -> 0xA6, which renders as a broken bar
#   CP65001                     round-trips
#
# So a stock 437 console draws the wordmark perfectly and never needed the
# UTF-8 switch at all. Keying off the codepage declared it incapable and
# printed the `#` fallback to the machines that least needed it.
#
# 1252 genuinely cannot, and that is the case worth switching for.
function Test-BlockGlyphs {
    try {
        $enc = [Console]::OutputEncoding
        $probe = [string][char]0x2588 + [string][char]0x2591
        return ($enc.GetString($enc.GetBytes($probe)) -eq $probe)
    } catch {
        return $false
    }
}

# Defined BEFORE the block below, which calls it: PowerShell resolves functions
# at run time, so a call above the definition is a runtime error rather than a
# parse one — the kind that only shows up on the machine you cannot test on.
function Restore-Console {
    if ($null -ne $script:PrevEncoding) {
        try { [Console]::OutputEncoding = $script:PrevEncoding } catch { }
        $script:PrevEncoding = $null
    }
}

$script:PrevEncoding = $null
$script:Unicode = $false
$script:AsciiForced = ($Ascii -or $env:YEET_ASCII)

# Only when there is a console to reconfigure. Redirected — CI, a transcript —
# the wordmark is not drawn at all, so there is nothing to gain by changing the
# encoding of a stream somebody else owns.
if ($script:Tty -and -not $script:AsciiForced) {
    if (Test-BlockGlyphs) {
        $script:Unicode = $true
    } else {
        # Ask for UTF-8, then ask the SAME question again rather than assuming
        # the assignment worked. Assigning Console::OutputEncoding calls
        # SetConsoleOutputCP, so this reconfigures the console itself.
        try {
            $script:PrevEncoding = [Console]::OutputEncoding
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
            $script:Unicode = Test-BlockGlyphs
            if (-not $script:Unicode) { Restore-Console }
        } catch {
            $script:Unicode = $false
        }
    }
}

# WHAT THIS STILL CANNOT SEE is the font. A PS 5.1 console set to the raster
# "Terminal" font cannot draw U+2588 at any codepage, and no API asks a console
# what font it is using. `-Ascii` / $env:YEET_ASCII is the stated way out, and
# docs/VERIFY-WINDOWS.md is how we find out whether it is needed in practice.

# The encoding is restored on every exit path, not only the happy one: this
# trap catches a terminating error, `Stop-Install` restores before exiting, and
# the last line of the script restores after the summary. A `finally` around
# the whole body would be the tidier shape and would also cover Ctrl-C; it is
# not worth re-indenting 300 lines of a file nobody on this team can execute.
trap {
    Restore-Console
    break
}

# --- the sunset ---------------------------------------------------------------
# THE SAME TWELVE STOPS install.sh USES, sampled from `theme.sunset()` — the
# function that also draws assets/yeet.svg — so the wordmark is one palette
# everywhere instead of three that drifted.
#
# WHY NOT `Write-Host -ForegroundColor`: it can only reach the console's
# sixteen. `DarkBlue`, `Magenta` and `Yellow` are what a six-stop sunset
# collapses into, which is why the Windows wordmark read as three flat bands of
# blue, purple and orange while the same six stops on macOS read as a gradient.
# Sixteen colours cannot express this and no amount of picking better names
# fixes that.
#
# So: real escapes when the host can process them. `SupportsVirtualTerminal` is
# what PowerShell answers for a console with ENABLE_VIRTUAL_TERMINAL_PROCESSING
# on — Windows Terminal always, conhost on Windows 10 1703 and later. Where it
# is false the sixteen-colour version is still there, unchanged.
$script:Esc = [char]27
$script:Vt = $false
try { $script:Vt = [bool]$Host.UI.SupportsVirtualTerminal } catch { $script:Vt = $false }

$script:RampRgb = @(
    '95;104;216', '108;101;216', '121;97;216', '141;98;210',
    '165;103;200', '188;107;190', '208;115;176', '226;125;160',
    '235;139;140', '243;155;124', '249;173;125', '255;192;125'
)
$script:Ramp = @()
foreach ($rgb in $script:RampRgb) { $script:Ramp += "$($script:Esc)[38;2;${rgb}m" }
$script:Reset = "$($script:Esc)[0m"
$script:Dim = "$($script:Esc)[38;5;238m"

#: Six rows, twelve stops — every other one, top of the letters to the baseline.
$script:WordmarkStops = @(0, 2, 4, 7, 9, 11)

function Write-Plain([string]$Text) { Write-Host $Text }

function Write-Colour([string]$Text, [string]$Colour) {
    if ($script:Tty) { Write-Host $Text -ForegroundColor $Colour } else { Write-Host $Text }
}

# --- the progress bar --------------------------------------------------------
# One bar, full width, and on a console it is the ONLY thing under the
# wordmark. install.sh does the same and for the same reason: a four-step
# install narrating its own bookkeeping tells you what it is doing instead of
# how much is left, and those lines are gone from your attention a second
# later. Redirected — a CI log, a transcript pasted into an issue — every line
# prints instead, because that is where the record has to be complete.
$script:Pct = 0
$script:BarOn = $false
$script:BarLabel = ''

function Get-ConsoleWidth {
    # 80 when it cannot be known: every console is at least that wide, and a
    # bar computed from a zero width prints nothing at all.
    try {
        $w = $Host.UI.RawUI.WindowSize.Width
        if ($w -and $w -gt 20) { return $w }
    } catch { }
    return 80
}

#: The wordmark's sunset, in the six console colours Write-Banner already uses.
#: The bar runs the same ramp left to right that the letters run top to bottom,
#: so the thing filling up is visibly the same object as the thing above it.
#: Write-Host cannot colour parts of one string, so the bar is written as six
#: -NoNewline segments on one line.
$script:BarBands = @('DarkBlue', 'DarkMagenta', 'Magenta', 'Magenta', 'Yellow', 'Yellow')

function Write-Bar {
    if (-not $script:Tty) { return }
    $cols = Get-ConsoleWidth
    # Two leading spaces, the brackets, a space, and `100%` — the fixed chrome
    # the bar itself has to leave room for, plus one column of slack so a full
    # bar never touches the last cell and wraps the line.
    $room = $cols - 11

    # A FIXED label field, not one that sizes to its contents: a field that
    # grows makes the bar change length whenever the label does, and a bar that
    # twitches while the percentage stands still looks like the percentage is
    # wrong. Under 60 columns the label is dropped rather than squeezed.
    $labelW = 0
    if ($cols -ge 60) {
        $labelW = 26
        if ([int]($cols / 3) -lt $labelW) { $labelW = [int]($cols / 3) }
    }
    $width = $room - $labelW - 2
    if ($width -lt 10) { $labelW = 0; $width = $room }
    if ($width -lt 10) { $width = 10 }

    $fill = [int]($script:Pct * $width / 100)
    if ($fill -gt $width) { $fill = $width }
    if ($script:Unicode) { $full = [char]0x2588; $empty = [char]0x2591 } else { $full = '#'; $empty = '-' }

    $pct = ("{0,3}" -f $script:Pct)
    if ($script:Vt) {
        # Twelve stops, one escape each, assembled into a single write. One
        # write matters: `-NoNewline` in a loop is a flush per segment, and on
        # a 5.1 console that flickers visibly at ten frames a second.
        $line = "`r  ["
        $drawn = 0
        for ($s = 0; $s -lt 12; $s++) {
            $upto = [Math]::Min([int](($s + 1) * $width / 12), $fill)
            if ($upto -gt $drawn) {
                $line += $script:Ramp[$s] + (New-Object string $full, ($upto - $drawn))
                $drawn = $upto
            }
        }
        if ($fill -gt $drawn) { $line += (New-Object string $full, ($fill - $drawn)); $drawn = $fill }
        if ($width -gt $drawn) {
            $line += $script:Dim + (New-Object string $empty, ($width - $drawn))
        }
        $line += $script:Reset + "] $pct%"
        Write-Host $line -NoNewline
    } else {
        Write-Host "`r  [" -NoNewline
        $drawn = 0
        for ($b = 0; $b -lt 6; $b++) {
            $upto = [Math]::Min([int](($b + 1) * $width / 6), $fill)
            if ($upto -gt $drawn) {
                Write-Host (New-Object string $full, ($upto - $drawn)) -NoNewline -ForegroundColor $script:BarBands[$b]
                $drawn = $upto
            }
        }
        if ($width - $drawn -gt 0) {
            Write-Host (New-Object string $empty, ($width - $drawn)) -NoNewline -ForegroundColor DarkGray
        }
        Write-Host "] $pct%" -NoNewline
    }
    if ($labelW -gt 0) {
        $text = "$($script:BarLabel)"
        if ($text.Length -gt $labelW) { $text = $text.Substring(0, $labelW) }
        Write-Host ("  " + $text.PadRight($labelW)) -NoNewline -ForegroundColor DarkGray
    }
    $script:BarOn = $true
}

function Clear-Bar {
    if (-not $script:BarOn) { return }
    # No ANSI: 5.1 consoles do not all have VT processing on. Overwrite the
    # line with spaces and come back to the start of it.
    Write-Host ("`r" + (' ' * ((Get-ConsoleWidth) - 1)) + "`r") -NoNewline
    $script:BarOn = $false
}

function Complete-Bar {
    if (-not $script:Tty) { return }
    $script:Pct = 100
    Write-Bar
    Write-Host ''
    $script:BarOn = $false
}

function Set-Progress([int]$Pct) {
    if ($Pct -gt $script:Pct) { $script:Pct = $Pct }
    Write-Bar
}

$script:StepNo = 0
function Write-Step([string]$Text) {
    $script:StepNo++
    # A floor, never an assignment: a later step must not run the bar
    # backwards, which reads as the installer losing its place.
    $floor = [int](($script:StepNo - 1) * 100 / $TotalSteps)
    if ($floor -gt $script:Pct) { $script:Pct = $floor }
    if (-not $script:Tty) {
        Write-Colour "[$($script:StepNo)/$TotalSteps] $Text" 'Yellow'
        return
    }
    $script:BarLabel = $Text
    Write-Bar
}

function Write-Ok([string]$Text) {
    if (-not $script:Tty) { Write-Colour "      ok  $Text" 'Green'; return }
    $script:BarLabel = $Text
    Write-Bar
}
function Write-Info([string]$Text) {
    if (-not $script:Tty) { Write-Plain "      $Text"; return }
    $script:BarLabel = $Text
    Write-Bar
}
# Warnings print on a console TOO. One that scrolled past inside a progress bar
# was never delivered.
function Write-Warn([string]$Text) {
    Clear-Bar
    Write-Colour "      !   $Text" 'Yellow'
    Write-Bar
}

function Stop-Install([string]$Text) {
    Clear-Bar
    Restore-Console
    Write-Host ''
    Write-Colour "  xx  $Text" 'Red'
    Write-Host ''
    exit 1
}

function Write-Banner {
    if (-not $script:Tty) { Write-Plain 'yeet installer'; Write-Host ''; return }
    # The same six rows install.sh prints, in the same sunset order, in
    # whichever alphabet this console can write.
    #
    # The ASCII form is not the rare path here — it is the DEFAULT one. Windows
    # PowerShell 5.1 runs on codepage 437 or 1252 on a stock box, never 65001,
    # and 5.1 is what this file exists to support. Gating the only wordmark on
    # UTF-8 meant the machines this installer most targets were the ones that
    # never saw it.
    if ($script:Unicode) {
        $rows = @(
            '  ████     ████  █████████  █████████  █████████████',
            '   ████   ████   ████       ████            ████    ',
            '    ████ ████    ███████    ███████         ████    ',
            '     ███████     ███████    ███████         ████    ',
            '       ████      ████       ████            ████    ',
            '       ████      █████████  █████████       ████    '
        )
    } else {
        $rows = @(
            '  ####     ####  #########  #########  #############',
            '   ####   ####   ####       ####            ####    ',
            '    #### ####    #######    #######         ####    ',
            '     #######     #######    #######         ####    ',
            '       ####      ####       ####            ####    ',
            '       ####      #########  #########       ####    '
        )
    }
    Write-Host ''
    if ($script:Vt) {
        # Six exact stops out of the twelve, so the letters fade the way the
        # SVG does rather than stepping through three console colours.
        for ($i = 0; $i -lt $rows.Count; $i++) {
            $stop = $script:Ramp[$script:WordmarkStops[$i]]
            Write-Host ($stop + $rows[$i] + $script:Reset)
        }
    } else {
        # Sixteen colours is all this host has. Kept because it is still a
        # wordmark, and a flat one beats a screen of escape codes printed
        # literally on a console that cannot process them.
        $colours = @('DarkBlue', 'DarkMagenta', 'Magenta', 'Magenta', 'Yellow', 'Yellow')
        for ($i = 0; $i -lt $rows.Count; $i++) {
            Write-Host $rows[$i] -ForegroundColor $colours[$i]
        }
    }
    Write-Host ''
    Write-Plain '  a local GitHub Actions runner, with a dialect of its own'
    Write-Host ''
}

# --- helpers -----------------------------------------------------------------

function Invoke-Native {
    <#
      Run a native command with stderr treated as OUTPUT rather than as failure,
      and hand back whatever it wrote.

      THE SAME TRAP `Invoke-Quiet` DOCUMENTS, at the call sites that are not
      `Invoke-Quiet`. With `$ErrorActionPreference = 'Stop'` in force, ANY
      native command writing to stderr raises a terminating NativeCommandError
      — and a native command writing to stderr is not an error, it is a native
      command talking.

      `docker info` on a machine with no daemon is the case that proved it: the
      install had finished, all four steps green, and the summary line that
      merely asks whether Docker is up killed the script with exit 1.

      A scriptblock rather than an exe plus args, so each call site keeps its
      own redirection (`*> $null`, `2>$null`, `*> $log`) and its own splatting.
      $LASTEXITCODE is global and survives the call.

      WHY THE SCOPE QUALIFIERS, and why this function did not work without them:
      a scriptblock is bound to the scope it was WRITTEN in, not to the one it
      is invoked from. `& $Body` runs the caller's scriptblock in a child of the
      CALLER'S scope, so a plain `$ErrorActionPreference = 'Continue'` here
      created a local variable that the scriptblock could never see — it kept
      resolving the name up its own chain to the script-scope 'Stop' at the top
      of this file. The preference has to be changed where the lookup will
      actually land, which is script scope (and global, for the `irm | iex`
      form, where the script's top level IS the caller's global scope).

      That is the whole reason pip's "Running command git clone ..." on stderr
      still killed the install at step 3 of 4 after this function existed.
    #>
    param([scriptblock]$Body)

    $prevScript = $script:ErrorActionPreference
    $prevGlobal = $global:ErrorActionPreference
    $script:ErrorActionPreference = 'Continue'
    $global:ErrorActionPreference = 'Continue'
    try {
        & $Body
    } finally {
        $script:ErrorActionPreference = $prevScript
        $global:ErrorActionPreference = $prevGlobal
    }
}

function Test-Elevated {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal $id
        return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
    } catch {
        return $false
    }
}

function Publish-EnvironmentChange {
    <#
      Broadcast WM_SETTINGCHANGE so Explorer — and everything launched from it
      afterwards — rereads the environment without a sign-out.

      Best effort by design, and called AFTER the value is already written: a
      locked-down machine where `Add-Type` cannot compile still got the PATH
      entry it asked for, and the only cost is that the user opens a new
      terminal rather than a new tab. `SendMessageTimeout`, not `SendMessage`:
      one hung top-level window must not hang an installer.
    #>
    try {
        if (-not ('Yeet.NativeEnv' -as [type])) {
            Add-Type -Namespace Yeet -Name NativeEnv -MemberDefinition @'
[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam,
    string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@ -ErrorAction Stop
        }
        $unused = [UIntPtr]::Zero
        # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, one second.
        [void][Yeet.NativeEnv]::SendMessageTimeout(
            [IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 1000, [ref]$unused)
    } catch { }
}

function Add-PathEntry {
    <#
      Add one directory to the persistent PATH. Returns 'added', 'present' or
      'denied' — never throws, because a PATH edit that fails must not lose the
      install that already succeeded.

      THROUGH THE REGISTRY, not `[Environment]::SetEnvironmentVariable`, and the
      difference is not cosmetic: that API writes REG_SZ. A user PATH that held
      `%USERPROFILE%\bin` is REG_EXPAND_SZ, and rewriting it as a plain string
      turns every variable in it into a literal — so an installer that only
      meant to append one entry silently breaks entries it never touched. The
      value kind is read and preserved here.

      `setx` has the same problem plus a worse one: it truncates any PATH longer
      than 1024 characters, and a corporate PATH routinely is.

      The value is read UNEXPANDED for the same reason.
    #>
    param([string]$Dir, [string]$Scope = 'User')

    if ($Scope -eq 'Machine') {
        $root = [Microsoft.Win32.Registry]::LocalMachine
        $sub = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    } else {
        $root = [Microsoft.Win32.Registry]::CurrentUser
        $sub = 'Environment'
    }

    $key = $null
    try {
        $key = $root.OpenSubKey($sub, $true)
        if ($null -eq $key) { return 'denied' }
        $current = [string]$key.GetValue(
            'Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        foreach ($entry in ($current -split ';')) {
            if ($entry -and ($entry.TrimEnd('\') -ieq $Dir.TrimEnd('\'))) { return 'present' }
        }
        $kind = [Microsoft.Win32.RegistryValueKind]::ExpandString
        try {
            if ($key.GetValueKind('Path') -eq [Microsoft.Win32.RegistryValueKind]::String) {
                $kind = [Microsoft.Win32.RegistryValueKind]::String
            }
        } catch { }
        $updated = if ($current) { "$current;$Dir" } else { $Dir }
        $key.SetValue('Path', $updated, $kind)
        return 'added'
    } catch {
        return 'denied'
    } finally {
        if ($null -ne $key) { $key.Close() }
    }
}

function Invoke-Quiet {
    <#
      Run a command, keep its output for the failure path only. pip's resolver
      output is forty lines nobody reads, right up until it fails and every one
      of them matters — so it goes to the log and is printed only then.
    #>
    param([string]$Label, [string]$Exe, [string[]]$Arguments, [int]$Target = 0)

    $script:BarLabel = $Label
    Write-Info "$Label..."
    # Half the remaining distance before the work, the rest after it. The call
    # below is synchronous — a native command cannot be polled without giving
    # up the splatted call operator that keeps `C:\Users\Tamizh Selvan\`
    # quoted correctly — so the bar cannot creep during it. Two movements per
    # long step is what can honestly be shown.
    if ($Target -gt 0) { Set-Progress ([int](($script:Pct + $Target) / 2)) }
    $log = Join-Path $HomeDir 'install.log'

    # Through `Invoke-Native` like every other native call in this file. pip
    # narrates its work on stderr — "Running command git clone
    # --filter=blob:none --quiet ..." — and this is the line where treating
    # that as a failure killed the install at step 3 of 4, on a progress
    # message, with a stack trace naming this file and not pip.
    #
    # `*> $log` makes it worse rather than better: redirecting the stream is
    # what wraps stderr as ErrorRecords in the first place. The exit code is
    # the only thing that decides whether this worked, which is what the return
    # below has always used.
    #
    # The call operator with a SPLATTED ARRAY stays inside the scriptblock, so
    # a path with a space in it is still one argument. `C:\Users\Tamizh
    # Selvan\` is the classic way that breaks, and it is why this cannot
    # become a string-quoted command line.
    Invoke-Native { & $Exe @Arguments *> $log }
    if ($Target -gt 0 -and $LASTEXITCODE -eq 0) { Set-Progress $Target }
    return ($LASTEXITCODE -eq 0)
}

function Get-PythonVersion([string]$Exe) {
    try {
        $out = Invoke-Native { & $Exe -c 'import platform; print(platform.python_version())' 2>$null }
        if ($LASTEXITCODE -ne 0) { return $null }
        return "$out".Trim()
    } catch {
        return $null
    }
}

function Get-RedirectedVenvHelp([string]$VenvDir) {
    @"
the virtualenv was created somewhere other than $VenvDir.

      That is what a Microsoft Store Python does: it runs in an app container
      that redirects writes under %LOCALAPPDATA% into its own LocalCache, so
      the interpreter this installer needs is not where it was put.

      Install Python from python.org (tick "Add python.exe to PATH"), or from
      winget:

          winget install Python.Python.3.12

      then re-run this installer. `py -3.12` will be preferred automatically.
"@
}

function Test-StorePython([string]$Exe, [string[]]$Prefix) {
    <#
      Is this the Microsoft Store build? Its writes under %LOCALAPPDATA% are
      redirected into the app container, which makes it unable to place a
      virtualenv where we ask for one — see Get-RedirectedVenvHelp.

      Asks the interpreter where it lives rather than guessing from the name:
      the Store ships an alias called `python3.exe` in
      %LOCALAPPDATA%\Microsoft\WindowsApps that looks like any other Python.
    #>
    try {
        $probe = $Prefix + @('-c', 'import sys; print(sys.executable)')
        $where = Invoke-Native { & $Exe @probe 2>$null }
        if ($LASTEXITCODE -ne 0) { return $false }
        return ("$where" -match 'WindowsApps|PythonSoftwareFoundation\.Python')
    } catch {
        return $false
    }
}

function Find-Python {
    <#
      Newest first. `py -3.13` before bare `python`, because the Microsoft Store
      stub named `python.exe` on a machine with no Python installed opens the
      Store instead of running anything, and the probe below is what rejects it.

      A Store Python that DOES run is rejected too, on a second pass. It passes
      every version check and then cannot put a virtualenv where it is told, so
      taking it means failing two steps later with a message about a cmdlet
      that is not recognised. Preferring anything else is the whole fix; if it
      is genuinely the only Python here, it is still used, and the venv check
      after creation explains what happened.
    #>
    $candidates = @()
    foreach ($minor in ($MaxTested..$MinMinor)) {
        $candidates += ,@('py', @("-3.$minor"))
    }
    $candidates += ,@('python3', @())
    $candidates += ,@('python', @())

    $fallback = $null
    foreach ($pair in $candidates) {
        $exe = $pair[0]
        $prefix = $pair[1]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $probe = $prefix + @('-c', "import sys; sys.exit(0 if sys.version_info >= (3, $MinMinor) else 1)")
        try {
            Invoke-Native { & $exe @probe 2>$null }
            if ($LASTEXITCODE -ne 0) { continue }
        } catch {
            continue
        }
        if (Test-StorePython $exe $prefix) {
            if (-not $fallback) { $fallback = ,@($exe, $prefix) }
            continue
        }
        return ,@($exe, $prefix)
    }
    if ($fallback) { Write-Warn 'only a Microsoft Store Python was found; it may redirect the virtualenv' }
    return $fallback
}

Write-Banner

# --- before anything is installed --------------------------------------------
# SAID FIRST, not in the summary, because by the summary it is advice about
# something the reader has already finished doing. Someone installing a
# workflow runner is about to run a workflow, and Docker Desktop takes a minute
# to come up — that minute is better spent now than after `yeet run` has
# already failed once.
#
# Precise about what needs it: the INSTALL does not, and saying it does would
# be a lie that turns a working offline install into a support question.
# `yeet run` does, for every job that is not `cooked_on: local`.
#
# Never fatal, and never a prompt: `irm | iex` has no console to answer one.
function Show-DockerPreflight {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Colour '  !   Docker is not installed.' 'Yellow'
        Write-Plain  '      Installing yeet does not need it. Running a workflow does -'
        Write-Plain  '      without it only `cooked_on: local` jobs will run.'
        Write-Host ''
        return
    }
    # Through Invoke-Native: `docker info` against a dead daemon writes to
    # stderr, and this is the exact call that used to kill the script.
    Invoke-Native { & docker info *> $null }
    if ($LASTEXITCODE -eq 0) {
        Write-Colour '  ok  Docker is running - container jobs will work.' 'Green'
        Write-Host ''
        return
    }
    Write-Colour '  !   Start Docker Desktop now, and leave it running.' 'Yellow'
    Write-Plain  '      yeet runs each job in a container. The install below does not'
    Write-Plain  '      need the daemon, but `yeet run` does - starting it now means it'
    Write-Plain  '      is ready by the time the install finishes.'
    Write-Host ''
}
Show-DockerPreflight

# --- 1. prerequisites --------------------------------------------------------
Write-Step 'Checking prerequisites'

# A corporate proxy is the normal case on a work laptop, and .NET does not read
# HTTPS_PROXY on its own the way curl does. pip reads the variables directly;
# this is for anything this script fetches itself.
if ($env:HTTPS_PROXY -or $env:HTTP_PROXY) {
    $proxy = if ($env:HTTPS_PROXY) { $env:HTTPS_PROXY } else { $env:HTTP_PROXY }
    try {
        [System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy($proxy, $true)
        Write-Ok "using proxy $proxy"
    } catch {
        Write-Warn "could not apply the proxy setting: $proxy"
    }
}

$Backend = 'venv'
$PythonExe = $null
$PythonPrefix = @()

if ((Get-Command uv -ErrorAction SilentlyContinue) -and -not $env:YEET_NO_UV) {
    $Backend = 'uv'
    Write-Ok 'uv found (fast path)'
}

$found = Find-Python
if ($found) {
    $PythonExe = $found[0]
    $PythonPrefix = $found[1]
    $ver = Get-PythonVersion $PythonExe
    Write-Ok "python $ver ($PythonExe $($PythonPrefix -join ' '))"
} elseif ($Backend -eq 'uv') {
    Write-Info 'no suitable Python on PATH - uv will fetch one'
} else {
    Stop-Install @"
no Python 3.$MinMinor or newer, and no uv to fetch one.

      winget install Python.Python.3.12

      or install uv, which brings its own Python:
      irm https://astral.sh/uv/install.ps1 | iex
"@
}

# `iex` has no script root — the file was never on disk. Read it the safe way
# rather than touching a variable that may not exist.
$here = Get-Variable -Name PSScriptRoot -ValueOnly -ErrorAction SilentlyContinue

# THE CLONE IS THE DEFAULT when the script is sitting in one. `.\install.ps1`
# inside a checkout you have been editing means the checkout, not `main` off
# the network, and -Local was a flag you had to already know existed.
#
# Asking for a -Version means "install that ref from GitHub", which is the one
# thing the clone next to the script is definitely not. Checked with
# $PSBoundParameters so the default value is not mistaken for a choice.
$autoLocal = $false
if (-not $Local -and -not $PSBoundParameters.ContainsKey('Version') -and -not $env:YEET_REF -and -not $env:YEET_REPO) {
    if ($here) {
        $marker = Join-Path $here 'pyproject.toml'
        # yeet's OWN pyproject, not merely one: this script copied into an
        # unrelated project must not install that project.
        if ((Test-Path $marker) -and (Select-String -Path $marker -Pattern '^name = "yeet"' -Quiet)) {
            $Local = $true
            $autoLocal = $true
        }
    }
}

if ($Local) {
    if (-not $here) {
        Stop-Install '-Local needs the script on disk: clone, then .\install.ps1 -Local'
    }
    $Source = $here
    if (-not (Test-Path (Join-Path $Source 'pyproject.toml'))) {
        Stop-Install "-Local: no pyproject.toml in $Source"
    }
    Write-Ok "installing from this clone ($Source)"
    if ($autoLocal) {
        # Named, not silent. Installing something other than what the user
        # thinks is the worst outcome available here.
        Write-Info 'pass -Version <ref> to install from GitHub instead'
    }
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    $Source = "git+$Repo@$Version"
    Write-Ok 'git found'
} else {
    # No git is normal on Windows. GitHub serves a tarball for every ref, and
    # pip installs one directly, so git is preferred rather than required.
    $Source = "$($Repo -replace '\.git$','')/archive/$Version.tar.gz"
    Write-Warn 'no git - installing from a source tarball instead'
}

# --- 2. an environment that belongs to yeet alone ----------------------------
Write-Step 'Creating an isolated environment'

# The version being replaced, read BEFORE the directory is removed. $null when
# there is no install, or it is too broken to answer.
#
# WHY THIS EXISTS. Re-running this script IS the upgrade path, and for anyone on
# 0.8 or earlier it is the ONLY one - `yeet upgrade` ships in 0.9, and a command
# cannot be back-fitted into a version already on someone's laptop. The script
# did the upgrade correctly and said "replacing the existing install", which is
# equally true of reinstalling the identical version. So the one question a
# person re-running this has - "did it actually move?" - was the one thing the
# output would not answer.
$OldVersion = $null
if (Test-Path $HomeDir) {
    $previous = Join-Path (Join-Path $HomeDir 'venv\Scripts') 'yeet.exe'
    if (Test-Path $previous) {
        # Through Invoke-Native: an install too broken to run is exactly the one
        # being replaced, and its stderr must not kill the replacement.
        $line = Invoke-Native { & $previous --version 2>$null } | Select-Object -First 1
        if ($line -match '\s(\S+)') { $OldVersion = $Matches[1] }
    }
    if ($OldVersion) { Write-Warn "replacing yeet $OldVersion" }
    else             { Write-Warn 'replacing the existing install' }
    # The launcher lives under $HomeDir; a running shell holding it open would
    # make this fail, which is a clearer error than a half-removed install.
    Remove-Item -Recurse -Force $HomeDir
}
New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null

$VenvDir = Join-Path $HomeDir 'venv'
$VenvPy = Join-Path (Join-Path $VenvDir 'Scripts') 'python.exe'

if ($Backend -eq 'uv') {
    $ok = Invoke-Quiet 'creating the virtualenv' 'uv' @(
        'venv', '--python', ">=3.$MinMinor,<3.$($MaxTested + 1)", $VenvDir
    ) 40
    if (-not $ok) {
        Write-Warn "no tested Python (3.$MinMinor-3.$MaxTested) - trying anything newer"
        $ok = Invoke-Quiet 'creating the virtualenv' 'uv' @('venv', '--python', ">=3.$MinMinor", $VenvDir) 40
    }
    if (-not $ok) {
        Get-Content (Join-Path $HomeDir 'install.log') -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Info $_ }
        Stop-Install 'uv could not create a virtualenv. Re-run with $env:YEET_NO_UV=1 to use python -m venv.'
    }
} else {
    # Through `Invoke-Quiet` like every other long native call, so its output
    # lands in the log instead of on the console. `python -m venv` under a Store
    # interpreter prints "Actual environment location may have moved due to
    # redirects, links or junctions" to STDERR — a warning, not a failure, and
    # one that printed as a red NativeCommandError block right in the middle of
    # a progress bar. The Test-Path below is what actually judges the result.
    $venvArgs = $PythonPrefix + @('-m', 'venv', $VenvDir)
    if (-not (Invoke-Quiet 'creating the virtualenv' $PythonExe $venvArgs 40)) {
        Stop-Install "could not create a virtualenv in $VenvDir"
    }

    # CHECK BEFORE USING IT. A Microsoft Store Python runs in an app container
    # that redirects writes under %LOCALAPPDATA% into
    #   ...\Packages\PythonSoftwareFoundation.Python.3.x_...\LocalCache\Local\
    # so `python -m venv` reports success, prints "Actual environment location
    # may have moved due to redirects, links or junctions", and puts the venv
    # somewhere other than where it was asked to. The next line then ran
    # `& $VenvPy` on a path that does not exist, and PowerShell reported it as
    # "The term '...\python.exe' is not recognized as the name of a cmdlet" —
    # which reads like a broken script rather than a redirected interpreter.
    if (-not (Test-Path $VenvPy)) { Stop-Install (Get-RedirectedVenvHelp $VenvDir) }

    Invoke-Quiet 'upgrading pip' $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip') 48 | Out-Null
}

if (-not (Test-Path $VenvPy)) { Stop-Install (Get-RedirectedVenvHelp $VenvDir) }
Write-Ok "$HomeDir (python $(Get-PythonVersion $VenvPy))"

# --- 3. the tool and its dependencies ----------------------------------------
Write-Step 'Installing yeet and its dependencies'
Write-Info "from $Source"

if ($Backend -eq 'uv') {
    $ok = Invoke-Quiet 'resolving and downloading' 'uv' @('pip', 'install', '--python', $VenvPy, $Source) 82
} else {
    $ok = Invoke-Quiet 'resolving and downloading' $VenvPy @('-m', 'pip', 'install', $Source) 82
}
if (-not $ok) {
    Write-Host ''
    Clear-Bar
    Get-Content (Join-Path $HomeDir 'install.log') -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Plain $_ }
    Stop-Install "the install failed. The full log is at $(Join-Path $HomeDir 'install.log')"
}

# `yeet run --tui` needs Textual, an optional extra in pyproject.toml. Optional
# is right for `pip install yeet`; this installer owns the venv it just built,
# so there is nobody else to inconvenience, and a documented flag that first
# asks you to install another package is a flag that does not work. Non-fatal
# and separate from $Source for the same reasons as in install.sh.
if ($Backend -eq 'uv') {
    $tui = Invoke-Quiet 'adding the dashboard' 'uv' @('pip', 'install', '--python', $VenvPy, 'textual>=0.80') 88
} else {
    $tui = Invoke-Quiet 'adding the dashboard' $VenvPy @('-m', 'pip', 'install', 'textual>=0.80') 88
}
if (-not $tui) { Write-Warn 'no dashboard: --tui will use the streaming view' }

$VenvYeet = Join-Path (Join-Path $VenvDir 'Scripts') 'yeet.exe'
$banner = Invoke-Native { & $VenvYeet --version 2>$null } | Select-Object -First 1
Write-Ok "$banner"

# The answer to "did it actually move?", said once, in the only place that knows
# both halves. An upgrade that looks identical to a no-op is why people run an
# installer three times and then open an issue.
$NewVersion = if ($banner -match '\s(\S+)') { $Matches[1] } else { $null }
if ($OldVersion -and $NewVersion) {
    if ($OldVersion -eq $NewVersion) { Write-Plain "      already on $NewVersion - reinstalled" }
    else { Write-Ok "upgraded $OldVersion -> $NewVersion" }
}

# --- 4. a launcher on PATH ---------------------------------------------------
Write-Step 'Putting yeet on your PATH'
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# A .cmd shim rather than a copy: cmd.exe and PowerShell both resolve a bare
# `yeet` through PATHEXT and find it, and it stays correct if the venv is
# rebuilt underneath. Every path is quoted — `C:\Users\Tamizh Selvan\` is the
# standard way this breaks.
$shim = @"
@echo off
rem Installed by the yeet installer. Delete this file and $HomeDir to remove.
"$VenvYeet" %*
"@
Set-Content -Path (Join-Path $BinDir 'yeet.cmd') -Value $shim -Encoding ASCII

# Self-deletion is the LAST line: cmd.exe reads a batch file from disk as it
# goes, so a script that removes itself in the middle stops there.
$uninstall = @"
@echo off
echo Removing $HomeDir
rmdir /s /q "$HomeDir"
del /q "$BinDir\yeet" 2>nul
echo Done. Remove $BinDir from PATH if you no longer want it.
del /q "%~f0"
"@
Set-Content -Path (Join-Path $BinDir 'yeet-uninstall.cmd') -Value $uninstall -Encoding ASCII
Write-Ok (Join-Path $BinDir 'yeet.cmd')

# AND AN EXTENSIONLESS SHELL SCRIPT NEXT TO IT, for Git Bash — the shell a large
# share of Windows developers actually type `yeet` into. bash does not use
# PATHEXT: it looks for the exact name `yeet` (appending only `.exe`), so a
# directory holding nothing but `yeet.cmd` gives "yeet: command not found" from
# the one shell whose PATH we just fixed.
#
# The two spellings cannot collide, which is what makes this safe: cmd.exe and
# PowerShell only ever find `yeet.cmd`, bash only ever finds `yeet`.
#
# Forward slashes in the interpreter path: this is read by a POSIX shell, where a
# backslash is an escape character, and `C:/Users/.../yeet.exe` is a path MSYS
# resolves happily. LF line endings for the same reason — `#!/bin/sh\r` is the
# single most confusing way a shell script can fail.
$posixTarget = $VenvYeet -replace '\\', '/'
$posixShim = "#!/bin/sh`n" +
    "# Installed by the yeet installer. Delete this file and $HomeDir to remove.`n" +
    "exec `"$posixTarget`" `"`$@`"`n"
# .NET writes the string exactly as given; Set-Content would translate the `n
# into the platform's CRLF and put the \r back into the shebang.
[System.IO.File]::WriteAllText(
    (Join-Path $BinDir 'yeet'), $posixShim, (New-Object System.Text.UTF8Encoding $false))
Write-Ok (Join-Path $BinDir 'yeet')

# THE PERSISTENT PATH. The user variable by default — it needs no elevation, it
# is what an isolated per-user install should touch, and cmd.exe, PowerShell and
# every new Git Bash window all read it at startup, so one edit covers all three.
#
# The machine variable is opt-in (`-System`, or $env:YEET_SYSTEM_PATH=1) and
# requires an elevated shell: it is shared with every other account on the box,
# and `irm | iex` is not a context in which to take that decision for someone.
# Asked for without elevation it says so rather than failing silently.
$PathOk = $false
$NeedsNewShell = $false

if ($env:YEET_NO_MODIFY_PATH) {
    Write-Warn "YEET_NO_MODIFY_PATH is set - add $BinDir to your PATH by hand"
} else {
    $result = Add-PathEntry $BinDir 'User'
    if ($result -eq 'added') {
        Write-Ok 'added to your user PATH (cmd, PowerShell, Git Bash)'
        $PathOk = $true
        $NeedsNewShell = $true
        Publish-EnvironmentChange
    } elseif ($result -eq 'present') {
        # Already persistent from an earlier install. This session may still not
        # have it, which is a different question and is answered below.
        $PathOk = $true
    } else {
        Write-Warn "could not write your user PATH - add $BinDir to it by hand"
    }

    if ($WantSystemPath) {
        if (-not (Test-Elevated)) {
            Write-Warn 'the system PATH needs an elevated prompt - user PATH only'
        } else {
            $machine = Add-PathEntry $BinDir 'Machine'
            if ($machine -eq 'added') {
                Write-Ok 'added to the system PATH (every account on this machine)'
                Publish-EnvironmentChange
            } elseif ($machine -ne 'present') {
                Write-Warn 'could not write the system PATH'
            }
        }
    }
}

# The PATH of the shell we are standing in, which no registry edit reaches: a
# process cannot change its parent's environment. `irm | iex` runs in the user's
# own session, so this one assignment is what makes `yeet` work immediately in
# the window they installed from — and it is prepended for the same reason the
# POSIX installer prepends: this yeet, not one an older install left behind.
$sessionHas = $false
foreach ($entry in ($env:PATH -split ';')) {
    if ($entry -and ($entry.TrimEnd('\') -ieq $BinDir.TrimEnd('\'))) { $sessionHas = $true; break }
}
if (-not $sessionHas) { $env:PATH = "$BinDir;$env:PATH" }

# --- what the user has, and what they do next --------------------------------
# Everything below writes whole lines and expects to own the cursor, so the bar
# is retired here rather than at the very end.
Complete-Bar
Write-Host ''

$dockerNote = 'No Docker - `runs-on: local` jobs still run (winget install Docker.DockerDesktop)'
$dockerColour = 'Yellow'
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Invoke-Native { & docker info *> $null }
    if ($LASTEXITCODE -eq 0) {
        $dockerNote = 'Docker is running - container jobs will work'
        $dockerColour = 'Green'
    } else {
        $dockerNote = 'Docker is installed but not running - start Docker Desktop'
    }
}

Write-Colour '  yeet is ready.' 'Green'
Write-Host ''
Write-Plain '  yeet doctor   is this machine set up to run a workflow?'
Write-Plain '  yeet scan     what is this project, and what flows does it have?'
Write-Plain '  yeet check    are the workflow files written correctly?'
Write-Plain '  yeet run      run them, in Docker or your own shell'
Write-Plain '  yeet upgrade  get the next version, without this script'
Write-Plain '  yeet --help   every command'
Write-Host ''
Write-Colour "  $dockerNote" $dockerColour

if ($NeedsNewShell) {
    # This window is already done — the assignment above did it. What is left to
    # say is about the OTHER shells, because a registry edit does not reach a
    # process that is already running.
    Write-Host ''
    Write-Plain '  -> ready in this window. cmd, Git Bash and any terminal already'
    Write-Plain '     open pick it up once reopened.'
} elseif (-not $PathOk) {
    Write-Host ''
    Write-Plain '  -> ready in this window only. To make it permanent, add to PATH:'
    Write-Plain "     $BinDir"
}
Write-Host ''
Write-Plain '  remove it again with  yeet-uninstall'
Write-Host ''

# The console was switched to UTF-8 to draw the wordmark. `irm | iex` runs in
# the user's own session, so it is handed back the way it was found.
Restore-Console
