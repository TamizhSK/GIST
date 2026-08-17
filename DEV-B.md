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