@echo off
REM Watchdog loop: keeps the dashboard alive on localhost:8501.
REM If streamlit crashes, waits 5s and relaunches. Runs hidden via dashboard_service.vbs.
chcp 65001 > nul
cd /d "%~dp0"

:loop
python -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false >> "%TEMP%\dashboard_service.log" 2>&1
timeout /t 5 /nobreak > nul
goto loop
