@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main_test.py --theme forest
) else (
  python main_test.py --theme forest
)
if errorlevel 1 (
  echo Install dependencies: python -m pip install -r requirements.txt
  pause
)
