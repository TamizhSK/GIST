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

.EXAMPLE
  irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 | iex

.EXAMPLE
  # Pinning a version needs the script on disk — `iex` cannot take arguments.
  irm https://raw.githubusercontent.com/TamizhSK/YEET/main/install.ps1 -OutFile i.ps1
  .\i.ps1 -Version v0.2

.NOTES
  Under a Restricted execution policy `irm | iex` is refused. That is the
  policy working, and the way past it for one command is:
      powershell -ExecutionPolicy Bypass -Command "irm <url> | iex"
#>

[CmdletBinding()]
param(
    [string]$Version = $(if ($env:YEET_REF) { $env:YEET_REF } else { 'main' }),
    [switch]$Local
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
$PathMarker = '# added by the yeet installer'

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

# The console codepage decides whether the block art can be WRITTEN at all.
# 65001 is UTF-8; anything else turns the wordmark into a screen of question
# marks, which is the worse first impression of the two.
#
# So ASK FOR IT rather than giving up. A stock Windows PowerShell 5.1 console
# starts on codepage 437 or 1252 and never on 65001, which meant the machines
# this file exists for were exactly the ones that got the ASCII fallback. In
# .NET, assigning Console::OutputEncoding calls SetConsoleOutputCP, so this
# changes the console itself and not merely how this process encodes.
#
# Verified afterwards rather than assumed — if the assignment is refused, or
# accepted and does not take, `$Unicode` stays false and the `#` wordmark is
# still there to fall back to. Restored on the way out by `Restore-Console`,
# because `irm | iex` runs in the user's own session and leaving their console
# reconfigured is not this script's business.
#
# Only when there is a console to reconfigure. Redirected — CI, a transcript —
# the wordmark is not drawn at all, so there is nothing to gain by changing the
# encoding of a stream somebody else owns.
$script:PrevEncoding = $null
$script:Unicode = $false
if ($script:Tty) {
    try {
        if ([Console]::OutputEncoding.CodePage -ne 65001) {
            $script:PrevEncoding = [Console]::OutputEncoding
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
        }
        $script:Unicode = ([Console]::OutputEncoding.CodePage -eq 65001)
    } catch {
        $script:Unicode = $false
    }
}

function Restore-Console {
    if ($null -ne $script:PrevEncoding) {
        try { [Console]::OutputEncoding = $script:PrevEncoding } catch { }
        $script:PrevEncoding = $null
    }
}

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

function Get-ConsoleWidth {
    # 80 when it cannot be known: every console is at least that wide, and a
    # bar computed from a zero width prints nothing at all.
    try {
        $w = $Host.UI.RawUI.WindowSize.Width
        if ($w -and $w -gt 20) { return $w }
    } catch { }
    return 80
}

function Write-Bar {
    if (-not $script:Tty) { return }
    # Two leading spaces, the brackets, a space, and `100%` — the fixed chrome
    # the bar itself has to leave room for, plus one column of slack so a full
    # bar never touches the last cell and wraps the line.
    $width = (Get-ConsoleWidth) - 11
    if ($width -lt 10) { $width = 10 }
    $fill = [int]($script:Pct * $width / 100)
    if ($fill -gt $width) { $fill = $width }
    if ($script:Unicode) { $full = [char]0x2588; $empty = [char]0x2591 } else { $full = '#'; $empty = '-' }
    $bar = (New-Object string $full, $fill) + (New-Object string $empty, ($width - $fill))
    $pct = ("{0,3}" -f $script:Pct)
    Write-Host ("`r  [$bar] $pct%") -NoNewline
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
    Write-Bar
}

function Write-Ok([string]$Text) {
    if (-not $script:Tty) { Write-Colour "      ok  $Text" 'Green'; return }
    Write-Bar
}
function Write-Info([string]$Text) {
    if (-not $script:Tty) { Write-Plain "      $Text"; return }
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
    $colours = @('DarkBlue', 'DarkMagenta', 'Magenta', 'Magenta', 'Yellow', 'Yellow')
    Write-Host ''
    for ($i = 0; $i -lt $rows.Count; $i++) {
        Write-Host $rows[$i] -ForegroundColor $colours[$i]
    }
    Write-Host ''
    Write-Plain '  a local GitHub Actions runner, with a dialect of its own'
    Write-Host ''
}

# --- helpers -----------------------------------------------------------------

function Invoke-Quiet {
    <#
      Run a command, keep its output for the failure path only. pip's resolver
      output is forty lines nobody reads, right up until it fails and every one
      of them matters — so it goes to the log and is printed only then.
    #>
    param([string]$Label, [string]$Exe, [string[]]$Arguments, [int]$Target = 0)

    Write-Info "$Label..."
    # Half the remaining distance before the work, the rest after it. The call
    # below is synchronous — a native command cannot be polled without giving
    # up the splatted call operator that keeps `C:\Users\Tamizh Selvan\`
    # quoted correctly — so the bar cannot creep during it. Two movements per
    # long step is what can honestly be shown.
    if ($Target -gt 0) { Set-Progress ([int](($script:Pct + $Target) / 2)) }
    $log = Join-Path $HomeDir 'install.log'

    # A NATIVE COMMAND WRITING TO STDERR IS NOT AN ERROR, and this is the line
    # where believing otherwise killed the install. pip narrates its work on
    # stderr — "Running command git clone --filter=blob:none --quiet ..." — and
    # with `$ErrorActionPreference = 'Stop'` in force, PowerShell turns each of
    # those records into a terminating NativeCommandError. The install died at
    # step 3 of 4 on a PROGRESS MESSAGE, with a stack trace pointing here and
    # nothing in it naming pip.
    #
    # `*> $log` makes it worse rather than better: redirecting the stream is
    # what wraps stderr as ErrorRecords in the first place.
    #
    # The exit code is the only thing that decides whether this worked, which
    # is what the return below has always used. So stderr goes to the log like
    # everything else, and `Stop` is restored on the way out for the cmdlets
    # that genuinely want it.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Call operator with a splatted array, so a path with a space in it
        # stays one argument. `C:\Users\Tamizh Selvan\` is the classic way this
        # breaks.
        & $Exe @Arguments *> $log
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($Target -gt 0 -and $LASTEXITCODE -eq 0) { Set-Progress $Target }
    return ($LASTEXITCODE -eq 0)
}

function Get-PythonVersion([string]$Exe) {
    try {
        $out = & $Exe -c 'import platform; print(platform.python_version())' 2>$null
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
        $where = & $Exe @probe 2>$null
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
            & $exe @probe 2>$null
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

if (Test-Path $HomeDir) {
    Write-Warn 'replacing the existing install'
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
    $venvArgs = $PythonPrefix + @('-m', 'venv', $VenvDir)
    & $PythonExe @venvArgs
    if ($LASTEXITCODE -ne 0) { Stop-Install "could not create a virtualenv in $VenvDir" }

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
$banner = & $VenvYeet --version 2>$null | Select-Object -First 1
Write-Ok "$banner"

# --- 4. a launcher on PATH ---------------------------------------------------
Write-Step 'Putting yeet on your PATH'
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# A .cmd shim rather than a copy: cmd.exe, PowerShell and Git Bash all execute
# it, and it stays correct if the venv is rebuilt underneath. Every path is
# quoted — `C:\Users\Tamizh Selvan\` is the standard way this breaks.
$shim = @"
@echo off
rem Installed by the yeet installer. Delete this file and $HomeDir to remove.
"$VenvYeet" %*
"@
Set-Content -Path (Join-Path $BinDir 'yeet.cmd') -Value $shim -Encoding ASCII

$uninstall = @"
@echo off
echo Removing $HomeDir
rmdir /s /q "$HomeDir"
echo Done. Remove $BinDir from PATH if you added it.
"@
Set-Content -Path (Join-Path $BinDir 'yeet-uninstall.cmd') -Value $uninstall -Encoding ASCII
Write-Ok (Join-Path $BinDir 'yeet.cmd')

# The USER PATH, never the machine one: the machine one needs elevation and is
# not ours to edit. Read from the registry rather than from $env:PATH, which is
# the merged value and would write the machine's entries into the user's.
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if ($null -eq $userPath) { $userPath = '' }
$entries = $userPath -split ';' | Where-Object { $_ -ne '' }
$PathOk = $false
foreach ($entry in $entries) {
    if ($entry.TrimEnd('\') -ieq $BinDir.TrimEnd('\')) { $PathOk = $true; break }
}

if (-not $PathOk -and -not $env:YEET_NO_MODIFY_PATH) {
    # Idempotent by construction: the check above is the marker. Running this
    # twice appends nothing the second time.
    $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    $env:PATH = "$env:PATH;$BinDir"
    Write-Ok 'added to your user PATH'
    $PathOk = $true
    $NeedsNewShell = $true
} else {
    $NeedsNewShell = $false
}

# --- what the user has, and what they do next --------------------------------
# Everything below writes whole lines and expects to own the cursor, so the bar
# is retired here rather than at the very end.
Complete-Bar
Write-Host ''

$dockerNote = 'No Docker - `runs-on: local` jobs still run (winget install Docker.DockerDesktop)'
$dockerColour = 'Yellow'
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker info *> $null
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
Write-Plain '  yeet --help   every command'
Write-Host ''
Write-Colour "  $dockerNote" $dockerColour

if ($NeedsNewShell) {
    Write-Host ''
    Write-Plain '  -> open a new terminal, or run:'
    Write-Plain "     `$env:PATH = `"$BinDir;`$env:PATH`""
}
Write-Host ''
Write-Plain '  remove it again with  yeet-uninstall'
Write-Host ''

# The console was switched to UTF-8 to draw the wordmark. `irm | iex` runs in
# the user's own session, so it is handed back the way it was found.
Restore-Console
