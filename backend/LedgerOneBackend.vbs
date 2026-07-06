' Silent launcher for LedgerOne backend - runs on logon and serves FastAPI in background.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "%ComSpec% /c """"C:\Users\arthu\AppData\Local\Programs\Python\Python312\python.exe"" ""server.py"" >> ""server.log"" 2>> ""server.err.log"""" "
WshShell.Run cmd, 0, False
