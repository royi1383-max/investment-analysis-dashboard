@echo off
chcp 65001 > nul
title Investment Dashboard — Enable Always-On
echo.
echo  ============================================
echo    Enable Always-On (start at Windows login)
echo  ============================================
echo.

cd /d "%~dp0"

REM ── Sanity checks before touching the Startup folder ────────────────────────
if not exist "dashboard_service.vbs" (
    echo  [ERROR] dashboard_service.vbs not found in this folder.
    echo  Run this file from inside the dashboard folder.
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [ERROR] .env not found — the dashboard has no API keys yet.
    echo  Run setup_and_run.bat FIRST, fill in your keys, confirm it works,
    echo  then come back and run this.
    pause
    exit /b 1
)

if not exist "%LOCALAPPDATA%\InvestmentDashboard\venv\Scripts\python.exe" (
    echo  [ERROR] Run setup_and_run.bat first - it creates the private environment.
    pause
    exit /b 1
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\InvestmentDashboard.lnk"

REM ── Create a shortcut to the hidden launcher in the Startup folder ──────────
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath='wscript.exe';" ^
  "$s.Arguments='\"%~dp0dashboard_service.vbs\"';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.Description='Investment Dashboard - always on at localhost:8501';" ^
  "$s.Save()"

if errorlevel 1 (
    echo  [ERROR] Could not create the startup shortcut.
    pause
    exit /b 1
)

echo  [OK] Always-on enabled.
echo.
echo  The dashboard will now start automatically at every Windows login,
echo  hidden in the background, and relaunch itself if it ever crashes.
echo.
echo  Open it any time at:  http://localhost:8501
echo.
echo  To turn this off, run: uninstall_autostart.bat
echo.
echo  Starting it now so you do not have to reboot...
start "" wscript.exe "%~dp0dashboard_service.vbs"
echo.
echo  Give it ~15 seconds, then open http://localhost:8501
echo.
pause
