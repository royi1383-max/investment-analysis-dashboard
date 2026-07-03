@echo off
chcp 65001 > nul
title Investment Dashboard — Setup & Run
echo.
echo  ============================================
echo    Investment Dashboard — Setup and Run
echo  ============================================
echo.

cd /d "%~dp0"

REM ── Check Python ────────────────────────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Install Python 3.10+ from https://python.org
    echo  Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM ── Check .env file ─────────────────────────────────────────────────────────
if not exist ".env" (
    echo  [SETUP] Creating .env from template...
    copy ".env.example" ".env" > nul
    echo.
    echo  *** ACTION REQUIRED ***
    echo  Open .env in Notepad and fill in your API keys:
    echo    ANTHROPIC_API_KEY  from: console.anthropic.com
    echo    FRED_API_KEY       from: fred.stlouisfed.org
    echo.
    echo  Dashboard works without keys but AI features will be disabled.
    echo.
    start notepad ".env"
    pause
)

REM ── Install packages ─────────────────────────────────────────────────────────
echo  [1/2] Installing packages (first run: 1-2 minutes)...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Package install failed. Check internet connection.
    pause
    exit /b 1
)

REM ── Launch ───────────────────────────────────────────────────────────────────
echo  [2/2] Launching dashboard...
echo.
echo  Open browser at: http://localhost:8501
echo  Press Ctrl+C to stop.
echo.
python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

pause
