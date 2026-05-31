' ЗАПУСК.vbs — Запуск WB Platform одним кликом
' Без чёрного окна CMD, без UAC

Dim objShell, objFSO, strDir, strBat

Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")

strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strBat = strDir & "\WB_PLATFORM.bat"

If Not objFSO.FileExists(strBat) Then
    MsgBox "Файл WB_PLATFORM.bat не найден в папке:" & vbCrLf & strDir, 16, "WB Platform"
    WScript.Quit
End If

' Запуск .bat в видимом окне (нужно для отслеживания прогресса)
objShell.Run "cmd.exe /c """ & strBat & """", 1, False

Set objShell = Nothing
Set objFSO   = Nothing
