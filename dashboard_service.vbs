' Launches dashboard_service.bat completely hidden (no console window).
Dim shell, fso, scriptDir
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c """ & scriptDir & "\dashboard_service.bat""", 0, False
