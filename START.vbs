' START.vbs - Double-click to launch WB Platform
' Window stays open so you can see progress

Dim objShell, objFSO, strDir, strBat

Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")

strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strBat = strDir & "\WB_PLATFORM.bat"

If Not objFSO.FileExists(strBat) Then
    MsgBox "WB_PLATFORM.bat not found in:" & vbCrLf & strDir, 16, "WB Platform Error"
    WScript.Quit
End If

objShell.Run "cmd.exe /k """ & strBat & """", 1, False

Set objShell = Nothing
Set objFSO   = Nothing
