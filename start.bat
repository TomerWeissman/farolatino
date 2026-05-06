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
    echo --------------------------------------------------------
    echo   Python isn't installed yet.
    echo --------------------------------------------------------
    echo.
    echo   Download Python 3.11 or newer from:
    echo       https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: check "Add Python to PATH" in the installer.
    echo.
    echo   After installing, double-click start.bat again.
    echo.
    pause
    exit /b 1
)

REM Check Python version >= 3.11
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo --------------------------------------------------------
    echo   Your Python is too old ^(need 3.11 or newer^).
    echo --------------------------------------------------------
    echo.
    echo   Install a newer version from:
    echo       https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo [OK] Python detected

REM 1.5 Check Claude Code (required: chat backend invokes `claude --print`)
where claude >nul 2>nul
if errorlevel 1 (
    echo --------------------------------------------------------
    echo   Claude Code isn't installed yet.
    echo --------------------------------------------------------
    echo.
    echo   FaroAI uses Claude Code as its chat engine.
    echo.
    echo   1. Install it from:  https://claude.com/claude-code
    echo   2. Open Terminal/PowerShell and run once:  claude login
    echo   3. Double-click start.bat again
    echo.
    pause
    exit /b 1
)
echo [OK] Claude Code on PATH

REM 2. .env file - auto-create empty if missing. The user adds API keys
REM    via the in-app Connections page once the dashboard opens.
if not exist ".env" (
    echo First-time setup: creating an empty .env ^(you'll add API keys in the app^)...
    type nul > ".env"
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
python -c "import fastapi" >nul 2>nul
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

REM (V2: removed .mcp.json generation block — tools execute in-process.)
goto :launch

:pipfail
echo.
echo [X] Dependency install failed.
echo     Full log: %~dp0.pip_install.log
echo.
pause
exit /b 1

:launch

REM 5c. Sanity-check the prebuilt frontend.
if not exist "%~dp0web\out\index.html" (
    echo [!] web\out\ is missing - frontend won't be served.
    echo     Re-clone the repo or run scripts\build_web.sh to rebuild it.
)

REM 6. Kill any stale Python process holding :8501 from a previous launch.
REM    Without this, the second start.bat run silently fails to bind and
REM    the new launch ends up talking to stale code.
for /f "tokens=5" %%P in ('netstat -aon ^| findstr ":8501.*LISTENING" 2^>nul') do (
    taskkill /F /PID %%P >nul 2>nul
)

REM 7. Launch FaroAI. Two paths:
REM    - Default: native desktop window (Phase 5 pywebview, no browser chrome).
REM    - --browser: legacy browser-tab UX, kept as a fallback.
echo.
echo Starting FaroAI...
echo (Close this window or press Ctrl+C to stop.)
echo.

if "%1"=="--browser" (
    start /b cmd /c "timeout /t 3 /nobreak >nul && start "" "http://localhost:8501""
    python -m uvicorn api.main:app --host 127.0.0.1 --port 8501 --log-level warning
) else (
    python -m core
)

pause
