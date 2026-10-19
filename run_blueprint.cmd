@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main_test.py --theme blueprint
) else (
  python main_test.py --theme blueprint
)
if errorlevel 1 pause
