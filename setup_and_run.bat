@echo off
chcp 65001 > nul
title Investment Dashboard — Setup and Run
echo.
echo  ============================================
echo    Investment Dashboard — Setup and Run
echo  ============================================
echo.

cd /d "%~dp0"

REM Private Python environment lives outside the project (short path, not cloud-synced).
set "VENV=%LOCALAPPDATA%\InvestmentDashboard\venv"

REM ── Check Python (3.12 or newer) ────────────────────────────────────────────
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.12 or newer was not found.
    echo  Install it from https://python.org
    echo  and tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM ── Check .env file ─────────────────────────────────────────────────────────
if not exist ".env" (
    echo  [SETUP] Creating .env from template...
    copy ".env.example" ".env" > nul
    echo.
    echo  *** ACTION REQUIRED ***
    echo  Open .env in Notepad and paste your own API keys.
    echo  The dashboard works without keys, but AI and macro features stay off.
    echo.
    start notepad ".env"
    pause
)

REM ── Private virtual environment (does not touch your system Python) ─────────
if not exist "%VENV%\Scripts\python.exe" (
    echo  [1/3] Creating private environment in %VENV% ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo  [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo  [2/3] Installing packages (first run: 1-3 minutes)...
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] Package install failed. Check your internet connection.
    pause
    exit /b 1
)

REM ── Launch (opens your browser; only reachable from this computer) ──────────
echo  [3/3] Launching dashboard...
echo.
echo  Address: http://localhost:8501   (press Ctrl+C here to stop)
echo.
"%VENV%\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
