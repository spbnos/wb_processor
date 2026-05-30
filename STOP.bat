@echo off
title WB Platform - STOP
echo Stopping WB Platform...
taskkill /FI "WINDOWTITLE eq WB-API*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq WB-Dashboard*" /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /PID %%P /F >nul 2>&1
echo [OK] WB Platform stopped.
pause
