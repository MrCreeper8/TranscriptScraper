Set shell = CreateObject("WScript.Shell")
appdir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
script = appdir & "\transcript_scraper.pyw"
shell.Run "pythonw.exe """ & script & """", 1, False
