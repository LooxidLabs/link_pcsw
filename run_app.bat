@echo off
REM 링크밴드 PC 소프트웨어 실행 (Windows)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python .vscode\main.py
pause
