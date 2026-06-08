@echo off
chcp 65001 > nul

set ROOT=D:\MyProject\wb_processor\scos

echo =====================================
echo Creating FastAPI structure...
echo =====================================

REM apps/api
mkdir "%ROOT%\apps\api"

REM src
mkdir "%ROOT%\apps\api\src"

REM api
mkdir "%ROOT%\apps\api\src\api"
mkdir "%ROOT%\apps\api\src\api\v1"

REM core
mkdir "%ROOT%\apps\api\src\core"

REM database
mkdir "%ROOT%\apps\api\src\db"

REM domain layers
mkdir "%ROOT%\apps\api\src\models"
mkdir "%ROOT%\apps\api\src\schemas"
mkdir "%ROOT%\apps\api\src\repositories"
mkdir "%ROOT%\apps\api\src\services"

REM background jobs
mkdir "%ROOT%\apps\api\src\tasks"

REM tests
mkdir "%ROOT%\apps\api\tests"
mkdir "%ROOT%\apps\api\tests\unit"
mkdir "%ROOT%\apps\api\tests\integration"

REM migrations
mkdir "%ROOT%\apps\api\alembic"
mkdir "%ROOT%\apps\api\alembic\versions"

REM docker
mkdir "%ROOT%\apps\api\docker"

REM logs
mkdir "%ROOT%\apps\api\logs"

REM temp
mkdir "%ROOT%\apps\api\tmp"

echo.
echo FastAPI structure created successfully.
pause
