@echo off
chcp 65001 > nul
title Investment Dashboard — Disable Always-On
echo.
echo  ============================================
echo    Disable Always-On
echo  ============================================
echo.

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\InvestmentDashboard.lnk"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo  [OK] Removed from Windows startup.
) else (
    echo  [INFO] Was not registered for startup — nothing to remove.
)

echo.
echo  Stopping any running dashboard...
REM Stop the watchdog first (a cmd.exe running dashboard_service.bat), then
REM the streamlit process it guards - otherwise the watchdog relaunches it.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*dashboard_service.bat*') -or ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*streamlit*run*app.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo  [OK] Done. The dashboard will no longer start on login.
echo.
echo  You can still launch it manually any time with:
echo    setup_and_run.bat
echo.
pause
