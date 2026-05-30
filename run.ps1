# Запуск WB Processor на Python 3.12 (рекомендуется; 3.14 может ломать pandas)
$Py = "py -3.12"
if ($args.Count -eq 0) {
    Write-Host "Usage: .\run.ps1 scan | run | status | mappings list ..."
    exit 1
}
& py -3.12 main.py @args
