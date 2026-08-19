> **Note:** the repository was named `TamizhSK/GIST` when this transcript was
> recorded. It is `TamizhSK/YEET` now, and the URLs below are left exactly as
> they were run. GitHub still redirects them.

1. Powershell installation command: while running this command out of 4 steps, 2 steps were positive but in the 3rd one it failed and the error encountered was:

python.exe :   Running command git clone --filter=blob:none --quiet https://github.com/TamizhSK/GIST 
'C:\Users\Gayathri\AppData\Local\Temp\pip-req-build-n7vfgat5'
At line:143 char:5
+     & $Exe @Arguments *> $log
+     ~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (  Running comma...build-n7vfgat5':String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError


2. Git Bash: Ran this command "curl -fsSL https://raw.githubusercontent.com/TamizhSK/GIST/main/install.sh | sh" and the error encountered was during the 3rd step out of 4 steps and the error is :

[3/4] Installing yeet and its dependencies
      from git+https://github.com/TamizhSK/GIST@main
                                                                      
      sh: line 249: /c/Users/Gayathri/.local/share/yeet/venv/bin/python: No such file or directory

  ✘ the install failed. The full log is at /c/Users/Gayathri/.local/share/yeet/install.log


3. Powershell Bypass: Ran this command " powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex" and the error was encountered during the 3rd step out of 4 steps and the error is :

[3/4] Installing yeet and its dependencies
      from git+https://github.com/TamizhSK/GIST@main
      resolving and downloading...
python.exe :   Running command git clone --filter=blob:none --quiet https://github.com/TamizhSK/GIST 
'C:\Users\Gayathri\AppData\Local\Temp\pip-req-build-jyjzfypk'
At line:156 char:5
+     & $Exe @Arguments *> $log
+     ~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (  Running comma...build-jyjzfypk':String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError

4.


the install.sh or powershell script should apply the PATH variable to system and users during installation itself so that when the user tries to use the commands, it runs on both git bash, cmd, and powershell, zsh too. without any struggles


there should be a documentation to show the genz convention of writing the yml file as well as using the commands to run the local runner.
the project should be able to find the yml files to run even when it is inside the workflows/*.yml

---

## What was done about each of these

| # | Report | Fix |
|---|---|---|
| 1, 3 | `NativeCommandError` from pip's stderr killed the PowerShell install at step 3/4 | `Invoke-Native` existed but did nothing: a scriptblock is bound to the scope it was WRITTEN in, so the function's local `$ErrorActionPreference = 'Continue'` was invisible to the `& $Body` it wrapped, which kept resolving to the script-scope `'Stop'`. It now sets the script and global ones, which is where the lookup lands. `python -m venv` moved behind `Invoke-Quiet` for the same reason — the Store-Python redirect warning is stderr too. |
| 2 | Git Bash: `venv/bin/python: No such file or directory` | Already fixed before this pass (`resolve_venv` looks for `venv/Scripts/python.exe` too, `install.sh`), and CI's `installer-gitbash` job holds it. |
| 4 | PATH must be set for system and users, so `yeet` runs in Git Bash, cmd, PowerShell and zsh | Both installers rewritten around this. POSIX: the line goes into every shell present (`.bashrc`/`.bash_profile`, `.zshrc`, fish, and always `.profile`), not only `$SHELL`'s. Windows: the **user PATH in the registry**, preserving its REG_EXPAND_SZ type (so a `%USERPROFILE%` entry is not turned into a literal) and never through `setx` (which truncates at 1024 chars), plus a `WM_SETTINGCHANGE` broadcast. Git Bash's `install.sh` now writes BOTH halves — the POSIX shim and a `yeet.cmd`, and the Windows user PATH. `-System` / `YEET_SYSTEM_PATH=1` adds the machine PATH, and says so when it needs elevation. |
| 5 | Documentation for the dialect and for running the local runner | [`docs/writing-flows.md`](docs/writing-flows.md) — the full alias table, a worked flow, where flows may live, every command and flag, exit codes, and how to write a step that survives Windows' pwsh default. Linked from `README.md` and `docs/README.md`. |
| 6 | Find flows under `workflows/*.yml` | `analyzer.discover` already ranked a bare `workflows/`; `yeet graph` was the last command still doing its own two-glob discovery, so it alone said "No flows found" about files `scan` had just listed. It uses the shared walk now. |

**Proved on this machine:** macOS and (in a container) Ubuntu 22.04 — profiles
written, idempotent on re-run, and a fresh `zsh -i` / `bash -l` resolves `yeet`.
**Proved in CI:** `.github/workflows/ci.yml` gained steps that install for real
on Windows and then assert the registry PATH is right, the `%USERPROFILE%`
canary survived, and cmd.exe, PowerShell and Git Bash each resolve a bare
`yeet` — from both installers.

