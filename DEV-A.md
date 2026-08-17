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