@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m tools.diagnosis_server
) else (
    python -m tools.diagnosis_server
)
if errorlevel 1 pause
