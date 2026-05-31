@echo off
title Статус WB Platform
echo.
echo  Проверка статуса WB Platform...
echo  ================================
echo.

python -c "import urllib.request,json; r=urllib.request.urlopen('http://127.0.0.1:8000/api/stats/health',timeout=3); d=json.loads(r.read()); print('  API:      OK — uptime',round(d.get('uptime_seconds',0)),'сек')" 2>nul || echo   API:      НЕ РАБОТАЕТ

python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173',timeout=3); print('  Dashboard: OK — http://127.0.0.1:5173')" 2>nul || echo   Dashboard: НЕ РАБОТАЕТ

echo.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% == 0 (echo   Порт 8000: ЗАНЯТ ^(API работает^)) else (echo   Порт 8000: свободен)

netstat -ano | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% == 0 (echo   Порт 5173: ЗАНЯТ ^(Dashboard работает^)) else (echo   Порт 5173: свободен)

echo.
pause
