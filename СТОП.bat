@echo off
title Остановка WB Platform
echo Останавливаем WB Platform...
echo.

taskkill /FI "WINDOWTITLE eq WB-API*"       /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq WB-Dashboard*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq WB-NPM*"       /F >nul 2>&1

:: Убиваем по порту на случай если заголовок изменился
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)

echo [OK] WB Platform остановлена.
echo.
pause
