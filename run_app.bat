@echo off
REM LINKBAND PC SW RUN (Windows)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    py -m venv .venv >nul 2>&1
    if errorlevel 1 (
        python -m venv .venv
        if errorlevel 1 (
            echo [ERROR] Failed to create virtual environment.
            echo Run manually: python -m venv .venv
            pause
            exit /b 1
        )
    )
)

call ".venv\Scripts\activate.bat"

python -c "import numpy, pkg_resources" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing required packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

python "app\main.py"
