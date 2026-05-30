@echo off
title WB Platform - STATUS
echo.
echo  WB Platform Status
echo  ==================
python -c "import urllib.request,json; r=urllib.request.urlopen('http://127.0.0.1:8000/api/stats/health',timeout=3); d=json.loads(r.read()); print('  API:       OK - uptime',round(d.get('uptime_seconds',0)),'sec')" 2>nul || echo   API:       NOT RUNNING
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173',timeout=3); print('  Dashboard: OK')" 2>nul || echo   Dashboard: NOT RUNNING
echo.
pause
