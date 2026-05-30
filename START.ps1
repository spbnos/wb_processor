# WB Intelligent Data Platform — PowerShell Startup Script
# Run with: powershell -ExecutionPolicy Bypass -File START.ps1

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  WB Intelligent Data Platform" -ForegroundColor White
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# 2. Install Python deps
Write-Host "`n[1/4] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt fastapi "uvicorn[standard]" httpx python-multipart rapidfuzz scikit-learn structlog prometheus_client 2>&1 | Out-Null
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

# 3. Create dirs
Write-Host "`n[2/4] Setting up directories..." -ForegroundColor Yellow
@("incoming", "processed", "failed", "data", "logs", "data\loaded", "data\feature_store", "data\registry") | ForEach-Object {
    $path = Join-Path $ProjectDir $_
    if (!(Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}
Write-Host "[OK] Directories ready" -ForegroundColor Green

# 4. Start FastAPI
Write-Host "`n[3/4] Starting FastAPI on http://localhost:8000 ..." -ForegroundColor Yellow
$apiProcess = Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$ProjectDir'; Write-Host 'WB API Starting...' -ForegroundColor Cyan; uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
) -PassThru
Start-Sleep -Seconds 4

# 5. Check API
Write-Host "`n[4/4] Verifying API health..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod "http://localhost:8000/api/stats/health" -TimeoutSec 5
    Write-Host "[OK] API Status: $($health.status) | Version: $($health.version)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] API still starting — check the API window" -ForegroundColor Yellow
}

# 6. Dashboard
Write-Host "`n=================================================" -ForegroundColor Cyan
Write-Host "  SYSTEM READY" -ForegroundColor White
Write-Host ""
Write-Host "  API:       http://localhost:8000" -ForegroundColor Green
Write-Host "  Swagger:   http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Metrics:   http://localhost:8000/metrics" -ForegroundColor Green
Write-Host ""

$dashPath = Join-Path $ProjectDir "dashboard"
if (Test-Path (Join-Path $dashPath "package.json")) {
    Write-Host "  Dashboard found. Starting dev server..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$dashPath'; if (!(Test-Path 'node_modules')) { npm install }; npm run dev -- --host 0.0.0.0"
    )
    Start-Sleep -Seconds 5
    Write-Host "  Dashboard: http://localhost:5173" -ForegroundColor Green
} else {
    Write-Host "  Dashboard: run 'cd dashboard && npm install && npm run dev -- --host 0.0.0.0'" -ForegroundColor Yellow
}

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to open browser..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
Start-Process "http://localhost:5173"
