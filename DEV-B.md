### Error:1

(.venv) PS C:\Users\shree\Projects\Documents\bmwproject\GIST> powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex"
  Y E E T   a local GitHub Actions runner
[1/4] Checking prerequisites
      ok  python 3.12.10 (python3 )
      ok  git found
[2/4] Creating an isolated environment
      !   replacing the existing install
Actual environment location may have moved due to redirects, links or junctions.
  Requested location: "C:\Users\shree\AppData\Local\yeet\venv\Scripts\python.exe"
  Actual location:    "C:\Users\shree\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Local\yeet\venv\Scripts\python.exe"
      upgrading pip...
iex : The term 
'C:\Users\shree\AppData\Local\yeet\venv\Scripts\python.exe' is not 
recognized as the name of a cmdlet, function, script file, or 
operable program. Check the spelling of the name, or if a path was 
included, verify that the path is correct and try again.
At line:1 char:72
+ ... ttps://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 
| iex
+                                                                     
  ~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\shree\...ipts 
   \python.exe:String) [Invoke-Expression], CommandNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException,Microsoft.Powe 
   rShell.Commands.InvokeExpressionCommand


### Error2:
   PS C:\Users\shree> irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex
  ####     ####  #########  #########  #############
   ####   ####   ####       ####            ####
    #### ####    #######    #######         ####
     #######     #######    #######         ####
       ####      ####       ####            ####
       ####      #########  #########       ####
  a local GitHub Actions runner, with a dialect of its own
[1/4] Checking prerequisites
      !   only a Microsoft Store Python was found; it may redirect the virtualenv
      ok  python 3.12.10 (python3 )
      ok  git found
[2/4] Creating an isolated environment
      upgrading pip...
      ok  C:\Users\shree\AppData\Local\yeet (python 3.12.10)
[3/4] Installing yeet and its dependencies
      from git+https://github.com/TamizhSK/GIST@main
      resolving and downloading...
      adding the dashboard...
      ok  yeet 0.2
[4/4] Putting yeet on your PATH
      ok  C:\Users\shree\AppData\Local\yeet\bin\yeet.cmd
      ok  added to your user PATH
docker.exe : ERROR: error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.48/info": open
//./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
At line:500 char:5
+     & docker info *> $null
+     ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (ERROR: error du...file specified.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError



### Error3:

PS C:\Users\shree> irm https://raw.githubusercontent.com/TamizhSK/GIST/main/install.ps1 | iex

  ####     ####  #########  #########  #############
   ####   ####   ####       ####            ####
    #### ####    #######    #######         ####
     #######     #######    #######         ####
       ####      ####       ####            ####
       ####      #########  #########       ####

  a local GitHub Actions runner, with a dialect of its own

[1/4] Checking prerequisites
      !   only a Microsoft Store Python was found; it may redirect the virtualenv
      ok  python 3.12.10 (python3 )
      ok  git found
[2/4] Creating an isolated environment
      !   replacing the existing install
      upgrading pip...
      ok  C:\Users\shree\AppData\Local\yeet (python 3.12.10)
[3/4] Installing yeet and its dependencies
      from git+https://github.com/TamizhSK/GIST@main
      resolving and downloading...
      adding the dashboard...
      ok  yeet 0.2
[4/4] Putting yeet on your PATH
      ok  C:\Users\shree\AppData\Local\yeet\bin\yeet.cmd

docker.exe : WARNING: daemon is not using the default seccomp profile
At line:500 char:5
+     & docker info *> $null
+     ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (WARNING: daemon...seccomp profile:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError