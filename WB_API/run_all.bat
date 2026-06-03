@echo off

cd /d D:\MyProject\wb_processor\WB_API

if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate

pip install -U pip
pip install playwright requests pyyaml beautifulsoup4

playwright install chromium

python scripts\run_all.py

pause