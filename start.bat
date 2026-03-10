@echo off
title Text Reader Server

:: Create desktop shortcut on first run
if not exist "%USERPROFILE%\Desktop\Text Reader.lnk" (
    echo Creating desktop shortcut...
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Text Reader.lnk'); $s.TargetPath = '%~dp0start.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0icon.ico'; $s.Description = 'Text Reader - Neural TTS'; $s.WindowStyle = 7; $s.Save()"
    echo Shortcut created on Desktop!
)

:: Install dependencies if needed
pip show edge-tts >nul 2>&1 || (
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
