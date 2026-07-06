' Silent launcher for LedgerOne frontend - runs on logon and serves Vite in background.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "%ComSpec% /c """"C:\Program Files\nodejs\npm.cmd"" run dev >> ""frontend.log"" 2>> ""frontend.err.log"""" "
WshShell.Run cmd, 0, False
