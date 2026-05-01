@echo off
REM FaroLatino A&R Dashboard - Windows launcher
REM Double-click this file in Explorer to start the dashboard.
REM First run: bootstraps Python venv + dependencies (~60-90s).
REM Later runs: launches in ~10s.

setlocal
cd /d "%~dp0"

echo.
echo ===========================================
echo   FaroLatino A^&R Dashboard
echo ===========================================
echo.

REM 1. Check Python
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python is not installed.
    echo.
    echo     Please install Python 3.11 or later from:
    echo     https://www.python.org/downloads/
    echo     IMPORTANT: Check "Add Python to PATH" during install.
    echo.
    echo     After installing, double-click this file again.
    echo.
    pause
    exit /b 1
)

REM Check Python version >= 3.11
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [X] Python 3.11 or later is required.
    echo     Install from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo [OK] Python detected

REM 1.5 Check Claude Code (required: chat backend invokes `claude --print`)
where claude >nul 2>nul
if errorlevel 1 (
    echo.
    echo [X] Claude Code is not installed.
    echo.
    echo     Install from: https://claude.com/claude-code
    echo     After installing, run `claude login` once in a terminal.
    echo.
    echo     Then double-click this file again.
    echo.
    pause
    exit /b 1
)
echo [OK] Claude Code on PATH

REM 2. Check .env file
if not exist ".env" (
    echo.
    echo [X] The .env file is missing.
    echo.
    echo     Drop the .env file you were sent into this folder:
    echo     %~dp0
    echo.
    echo     Then double-click this file again.
    echo.
    pause
    exit /b 1
)
echo [OK] .env present

REM 3. Create venv if missing
if not exist "venv" (
    echo.
    echo First-time setup: creating virtual environment ^(~30s^)...
    python -m venv venv
    echo [OK] Virtual environment created
)

REM 4. Activate venv
call venv\Scripts\activate.bat

REM 5. Install / update deps. Redirect pip stderr to a log file because
REM pip's HTTP-cache machinery emits benign-but-alarming warnings on some
REM setups. Real errors surface via exit code; log is available if needed.
python -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing dependencies ^(~60s, only on first run^)...
    python -m pip install --upgrade pip --quiet > "%~dp0.pip_install.log" 2>&1
    if errorlevel 1 goto :pipfail
    python -m pip install -r requirements.txt --quiet >> "%~dp0.pip_install.log" 2>&1
    if errorlevel 1 goto :pipfail
    echo [OK] Dependencies installed
    del /q "%~dp0.pip_install.log" >nul 2>nul
) else (
    python -m pip install -r requirements.txt --quiet >nul 2>nul
)

REM 5b. Generate .mcp.json so `claude --print` can spawn the FaroLatino
REM     MCP server with this snapshot's venv. Regenerated on every launch.
set "PY_BIN=%~dp0venv\Scripts\python.exe"
set "PY_BIN_JSON=%PY_BIN:\=\\%"
set "CWD_JSON=%~dp0"
set "CWD_JSON=%CWD_JSON:\=\\%"
> "%~dp0.mcp.json" (
    echo {
    echo   "mcpServers": {
    echo     "farolatino": {
    echo       "command": "%PY_BIN_JSON%",
    echo       "args": ["-m", "mcp_server"],
    echo       "cwd": "%CWD_JSON%"
    echo     }
    echo   }
    echo }
)
echo [OK] MCP config ready
goto :launch

:pipfail
echo.
echo [X] Dependency install failed.
echo     Full log: %~dp0.pip_install.log
echo.
pause
exit /b 1

:launch

REM 6. Open browser after a delay (parallel)
start /b cmd /c "timeout /t 3 /nobreak >nul && start "" "http://localhost:8501""

REM 7. Launch Streamlit
echo.
echo Starting dashboard...
echo (Browser will open automatically. Close this window or press Ctrl+C to stop.)
echo.
streamlit run streamlit_app/main.py --server.headless=true

pause
