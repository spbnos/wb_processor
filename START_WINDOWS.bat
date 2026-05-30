@echo off
echo =====================================================
echo  WB Intelligent Data Platform — Windows Startup
echo =====================================================
echo.

REM Check Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

REM Install Python deps
echo [1/4] Installing Python dependencies...
pip install -r requirements.txt fastapi uvicorn[standard] httpx python-multipart rapidfuzz scikit-learn structlog prometheus_client 2>nul
echo Done.

REM Init data dirs
echo [2/4] Creating directories...
if not exist "incoming" mkdir incoming
if not exist "processed" mkdir processed
if not exist "failed" mkdir failed
if not exist "data" mkdir data
if not exist "logs" mkdir logs
echo Done.

REM Start API in background
echo [3/4] Starting FastAPI backend on http://localhost:8000 ...
start "WB-API" cmd /k "cd /d %~dp0 && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul

REM Check API is up
echo [4/4] Checking API health...
curl -s http://localhost:8000/api/stats/health >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [OK] API is running at http://localhost:8000
    echo [OK] Swagger UI at http://localhost:8000/docs
) ELSE (
    echo [WARN] API may still be starting — check the WB-API window
)

echo.
echo =====================================================
echo  Dashboard: open dashboard\index.html in browser
echo  OR run: cd dashboard ^&^& npm install ^&^& npm run dev -- --host 0.0.0.0
echo  Then open: http://localhost:5173
echo =====================================================
echo.
pause
