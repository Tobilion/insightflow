@echo off
title InsightFlow - Stock Analysis
cd /d "%~dp0"

echo ==========================================
echo    InsightFlow
echo    Desktop Stock Analysis
echo ==========================================
echo.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py"
)
if not defined PY (
    echo [!] Python is not installed, or not on your PATH.
    echo     Install it from https://python.org and tick
    echo     "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" goto setup
goto ask

:setup
echo First run detected - creating a virtual environment...
echo.
call %PY% -m venv .venv
if errorlevel 1 (
    echo [!] Could not create the virtual environment.
    pause
    exit /b 1
)
echo Installing dependencies. PySide6 is large, so this can
echo take a few minutes on the first run...
call ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [!] Dependency install failed. Scroll up to see why.
    pause
    exit /b 1
)
echo.

:ask
echo How do you want to start?
echo.
echo   [1] Demo mode - bundled sample data, no API key needed
echo   [2] Live mode - fetches real data, needs an Alpha Vantage key
echo.
set "MODE="
set /p MODE=Choose 1 or 2 (just press Enter for demo):
if "%MODE%"=="2" goto live
goto demo

:demo
echo.
echo Launching InsightFlow in demo mode...
echo.
cd /d "%~dp0.."
"%~dp0.venv\Scripts\python.exe" -m insightflow.main --demo
goto done

:live
echo.
echo Launching InsightFlow in live mode...
echo.
cd /d "%~dp0.."
"%~dp0.venv\Scripts\python.exe" -m insightflow.main
goto done

:done
echo.
echo InsightFlow closed.
pause
