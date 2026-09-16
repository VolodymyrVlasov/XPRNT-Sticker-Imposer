@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo Checking for Python...

set "PYTHON_CMD="

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 --version >nul 2>nul
    if !errorlevel!==0 (
        set "PYTHON_CMD=py -3"
    )
)

if not defined PYTHON_CMD (
    python --version >nul 2>nul
    if !errorlevel!==0 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Python was not found on this computer.
    echo.
    echo If Windows just tried to open the Microsoft Store, that is NOT a real
    echo Python install. Instead:
    echo   1. Download Python from https://www.python.org/downloads/
    echo   2. During setup, check "Add python.exe to PATH"
    echo   3. If Python IS already installed but this still fails, disable the
    echo      alias at: Settings ^> Apps ^> Advanced app settings ^>
    echo      App execution aliases ^(turn OFF python.exe / python3.exe^)
    echo.
    pause
    exit /b 1
)

echo Using: !PYTHON_CMD!
echo.
echo Installing/updating dependencies from requirements.txt...
!PYTHON_CMD! -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies. See the error above.
    pause
    exit /b 1
)

echo.
echo Starting server...
!PYTHON_CMD! run_server.py
pause
