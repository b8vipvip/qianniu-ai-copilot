@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -U pip
python -m pip install -r requirements.txt
set PYTHONPATH=%cd%\src
python -m qianniu_ai_copilot.main
pause
