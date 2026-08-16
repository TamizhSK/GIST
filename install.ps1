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
  Install from the clone this script sits in. No network fetch of the source.

.EXAMPLE
  irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex

.EXAMPLE
  # Pinning a version needs the script on disk — `iex` cannot take arguments.
  irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 -OutFile i.ps1
  .\i.ps1 -Version v0.1.0

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
    if (-not $script:Unicode) {
        Write-Colour '  Y E E T   a local GitHub Actions runner' 'Yellow'
        Write-Host ''
        return
    }
    # The same six rows install.sh prints, in the same sunset order.
    $rows = @(
        '  ████     ████  █████████  █████████  █████████████',
        '   ████   ████   ████       ████            ████    ',
        '    ████ ████    ███████    ███████         ████    ',
        '     ███████     ███████    ███████         ████    ',
        '       ████      ████       ████            ████    ',
        '       ████      █████████  █████████       ████    '
    )
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
    # Call operator with a splatted array, so a path with a space in it stays
    # one argument. `C:\Users\Tamizh Selvan\` is the classic way this breaks.
    & $Exe @Arguments *> $log
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

function Find-Python {
    <#
      Newest first. `py -3.13` before bare `python`, because the Microsoft Store
      stub named `python.exe` on a machine with no Python installed opens the
      Store instead of running anything, and the probe below is what rejects it.
    #>
    $candidates = @()
    foreach ($minor in ($MaxTested..$MinMinor)) {
        $candidates += ,@('py', @("-3.$minor"))
    }
    $candidates += ,@('python3', @())
    $candidates += ,@('python', @())

    foreach ($pair in $candidates) {
        $exe = $pair[0]
        $prefix = $pair[1]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $probe = $prefix + @('-c', "import sys; sys.exit(0 if sys.version_info >= (3, $MinMinor) else 1)")
        try {
            & $exe @probe 2>$null
            if ($LASTEXITCODE -eq 0) { return ,@($exe, $prefix) }
        } catch {
            continue
        }
    }
    return $null
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

if ($Local) {
    # `iex` has no script root — the file was never on disk. Read it the safe
    # way rather than touching a variable that may not exist.
    $here = Get-Variable -Name PSScriptRoot -ValueOnly -ErrorAction SilentlyContinue
    if (-not $here) {
        Stop-Install '-Local needs the script on disk: clone, then .\install.ps1 -Local'
    }
    $Source = $here
    if (-not (Test-Path (Join-Path $Source 'pyproject.toml'))) {
        Stop-Install "-Local: no pyproject.toml in $Source"
    }
    Write-Ok "installing from this clone ($Source)"
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
    Invoke-Quiet 'upgrading pip' $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip') | Out-Null
}

if (-not (Test-Path $VenvPy)) { Stop-Install "no interpreter at $VenvPy" }
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
