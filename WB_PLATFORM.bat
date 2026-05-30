@echo off
setlocal EnableDelayedExpansion
title WB Platform
color 0A

set "P=%~dp0"
if "%P:~-1%"=="\" set "P=%P:~0,-1%"
set "PY="

echo.
echo *** WB INTELLIGENT DATA PLATFORM ***
echo ================================================
echo.

echo [1/5] Finding Python...
if exist "D:\Python312\python.exe" set "PY=D:\Python312\python.exe"
if exist "D:\Python311\python.exe" set "PY=D:\Python311\python.exe"
if exist "C:\Python312\python.exe" set "PY=C:\Python312\python.exe"
if exist "C:\Python311\python.exe" set "PY=C:\Python311\python.exe"
if "%PY%"=="" where python >nul 2>&1 && set "PY=python"
if "%PY%"=="" (
    echo [ERROR] Python not found. Get it from https://python.org
    pause
    exit /b 1
)
"%PY%" --version
echo [OK] Python found

echo.
echo [2/5] Installing dependencies...
"%PY%" -m pip install -q fastapi "uvicorn[standard]" httpx python-multipart rapidfuzz scikit-learn structlog prometheus_client pandas openpyxl watchdog rich click python-dotenv chardet SQLAlchemy >nul 2>&1
echo [OK] Dependencies ready

echo.
echo [3/5] Creating folders...
if not exist "%P%\incoming" mkdir "%P%\incoming"
if not exist "%P%\processed" mkdir "%P%\processed"
if not exist "%P%\failed" mkdir "%P%\failed"
if not exist "%P%\logs" mkdir "%P%\logs"
if not exist "%P%\data" mkdir "%P%\data"
if not exist "%P%\data\loaded" mkdir "%P%\data\loaded"
if not exist "%P%\data\registry" mkdir "%P%\data\registry"
if not exist "%P%\knowledge_base\documents" mkdir "%P%\knowledge_base\documents"
echo [OK] Folders ready

echo.
echo [4/5] Starting API on port 8000...
netstat -ano 2>nul | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% == 0 goto api_ok

start "WB-API" /min cmd /k "cd /d "%P%" && "%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
echo [..] Waiting for API...
set N=0
:api_loop
    set /a N+=1
    if %N% GTR 15 goto api_slow
    timeout /t 2 /nobreak >nul
    "%PY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/stats/health',timeout=2)" >nul 2>&1
    if %ERRORLEVEL%==0 goto api_ok
    goto api_loop
:api_slow
echo [WARN] API slow - see WB-API window in taskbar
goto dash
:api_ok
echo [OK] API running: http://127.0.0.1:8000

:dash
echo.
echo [5/5] Starting Dashboard on port 5173...
where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Node.js not found - get from https://nodejs.org
    goto done
)
netstat -ano 2>nul | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto dash_ok

if not exist "%P%\dashboard\node_modules" (
    echo [..] npm install - first run takes 1-2 min...
    cd /d "%P%\dashboard"
    npm install >nul 2>&1
    cd /d "%P%"
    echo [OK] npm done
)
start "WB-Dashboard" /min cmd /k "cd /d "%P%\dashboard" && npm run dev -- --host 0.0.0.0 --port 5173"
echo [..] Waiting for Dashboard...
set M=0
:dash_loop
    set /a M+=1
    if %M% GTR 20 goto dash_slow
    timeout /t 2 /nobreak >nul
    "%PY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173',timeout=2)" >nul 2>&1
    if %ERRORLEVEL%==0 goto dash_ok
    goto dash_loop
:dash_slow
echo [WARN] Dashboard slow - refresh browser in 15 sec
goto done
:dash_ok
echo [OK] Dashboard: http://127.0.0.1:5173

:done
echo.
echo ================================================
echo SYSTEM READY
echo   Dashboard : http://127.0.0.1:5173
echo   API       : http://127.0.0.1:8000
echo   Swagger   : http://127.0.0.1:8000/docs
echo ================================================
echo.
timeout /t 3 /nobreak >nul
netstat -ano 2>nul | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" http://127.0.0.1:5173
) else (
    start "" http://127.0.0.1:8000/docs
)
echo Minimize this window. To stop: run STOP.bat
