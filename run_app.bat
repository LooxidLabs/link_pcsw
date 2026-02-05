@echo off
REM LINKBAND PC SW RUN (Windows)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python .vscode\main.py
pause
