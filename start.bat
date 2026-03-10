@echo off
title Text Reader Server

:: Create desktop shortcut on first run
if not exist "%USERPROFILE%\Desktop\Text Reader.lnk" (
    powershell -ExecutionPolicy Bypass -File "%~dp0create-shortcut.ps1"
)

:: Install dependencies if needed
pip show edge-tts >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r "%~dp0requirements.txt"
)

echo.
echo Starting Text Reader...
echo Open http://localhost:8765 in your browser
echo.
start http://localhost:8765
python "%~dp0text-reader-server.py"
pause
