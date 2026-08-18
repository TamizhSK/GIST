<#
.SYNOPSIS
  yeet installer for Windows.

.DESCRIPTION
  irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex

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
  irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex

.EXAMPLE
  # Pinning a version needs the script on disk — `iex` cannot take arguments.
  irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 -OutFile i.ps1
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

$Repo = if ($env:YEET_REPO) { $env:YEET_REPO } else { 'https://github.com/TamizhSK/GIST' }
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
# 65001 is UTF-8; anything else gets the plain wordmark rather than a screen of
# question marks, which is the worse first impression of the two.
$script:Unicode = $false
try {
    $script:Unicode = ([Console]::OutputEncoding.CodePage -eq 65001)
} catch {
    $script:Unicode = $false
}

function Write-Plain([string]$Text) { Write-Host $Text }

function Write-Colour([string]$Text, [string]$Colour) {
    if ($script:Tty) { Write-Host $Text -ForegroundColor $Colour } else { Write-Host $Text }
}

$script:StepNo = 0
function Write-Step([string]$Text) {
    $script:StepNo++
    Write-Colour "[$($script:StepNo)/$TotalSteps] $Text" 'Yellow'
}

function Write-Ok([string]$Text) { Write-Colour "      ok  $Text" 'Green' }
function Write-Info([string]$Text) { Write-Plain "      $Text" }
function Write-Warn([string]$Text) { Write-Colour "      !   $Text" 'Yellow' }

function Stop-Install([string]$Text) {
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
    param([string]$Label, [string]$Exe, [string[]]$Arguments)

    Write-Info "$Label..."
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
    )
    if (-not $ok) {
        Write-Warn "no tested Python (3.$MinMinor-3.$MaxTested) - trying anything newer"
        $ok = Invoke-Quiet 'creating the virtualenv' 'uv' @('venv', '--python', ">=3.$MinMinor", $VenvDir)
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

    Invoke-Quiet 'upgrading pip' $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip') | Out-Null
}

if (-not (Test-Path $VenvPy)) { Stop-Install (Get-RedirectedVenvHelp $VenvDir) }
Write-Ok "$HomeDir (python $(Get-PythonVersion $VenvPy))"

# --- 3. the tool and its dependencies ----------------------------------------
Write-Step 'Installing yeet and its dependencies'
Write-Info "from $Source"

if ($Backend -eq 'uv') {
    $ok = Invoke-Quiet 'resolving and downloading' 'uv' @('pip', 'install', '--python', $VenvPy, $Source)
} else {
    $ok = Invoke-Quiet 'resolving and downloading' $VenvPy @('-m', 'pip', 'install', $Source)
}
if (-not $ok) {
    Write-Host ''
    Get-Content (Join-Path $HomeDir 'install.log') -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Info $_ }
    Stop-Install "the install failed. The full log is at $(Join-Path $HomeDir 'install.log')"
}

# `yeet run --tui` needs Textual, an optional extra in pyproject.toml. Optional
# is right for `pip install yeet`; this installer owns the venv it just built,
# so there is nobody else to inconvenience, and a documented flag that first
# asks you to install another package is a flag that does not work. Non-fatal
# and separate from $Source for the same reasons as in install.sh.
if ($Backend -eq 'uv') {
    $tui = Invoke-Quiet 'adding the dashboard' 'uv' @('pip', 'install', '--python', $VenvPy, 'textual>=0.80')
} else {
    $tui = Invoke-Quiet 'adding the dashboard' $VenvPy @('-m', 'pip', 'install', 'textual>=0.80')
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
