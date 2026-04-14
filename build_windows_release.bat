@echo off
setlocal

REM Build Windows 10/11 distributable (PyInstaller onedir)
cd /d "%~dp0"

set "APP_NAME=LINKBAND_PC_SW"
set "ENTRY_SCRIPT=.vscode\main.py"
set "BUILD_VENV=.venv-build"
set "RELEASE_DIR=release\windows"
set "DIST_DIR=dist\%APP_NAME%"

if not exist "%ENTRY_SCRIPT%" (
    echo [ERROR] Entry script not found: %ENTRY_SCRIPT%
    exit /b 1
)

if exist "%BUILD_VENV%\Scripts\python.exe" (
    echo [INFO] Reusing build virtual environment: %BUILD_VENV%
) else (
    echo [INFO] Creating build virtual environment...
    py -m venv "%BUILD_VENV%" >nul 2>&1
    if errorlevel 1 (
        python -m venv "%BUILD_VENV%"
        if errorlevel 1 (
            echo [ERROR] Failed to create build virtual environment.
            exit /b 1
        )
    )
)

call "%BUILD_VENV%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate build virtual environment.
    exit /b 1
)

echo [INFO] Installing dependencies for build...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install requirements / pyinstaller.
    exit /b 1
)

echo [INFO] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"

echo [INFO] Building %APP_NAME%...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "%APP_NAME%" ^
  --collect-all matplotlib ^
  --collect-all scipy ^
  --collect-all heartpy ^
  --collect-all bleak ^
  --hidden-import pkg_resources ^
  "%ENTRY_SCRIPT%"

if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

echo [INFO] Preparing release folder...
mkdir "%RELEASE_DIR%" >nul 2>&1
xcopy "%DIST_DIR%" "%RELEASE_DIR%\%APP_NAME%\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy build output to release folder.
    exit /b 1
)

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "%%~dp0%APP_NAME%\%APP_NAME%.exe"
) > "%RELEASE_DIR%\run_app.bat"

echo [OK] Build complete.
echo [OK] Run this file on Windows 10/11:
echo      %RELEASE_DIR%\run_app.bat
echo [OK] App folder:
echo      %RELEASE_DIR%\%APP_NAME%\

endlocal
exit /b 0
