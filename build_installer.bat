@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creez .venv et installez requirements-gpu.txt avant de compiler.
    exit /b 1
)
".venv\Scripts\python.exe" build_release.py
exit /b %errorlevel%
