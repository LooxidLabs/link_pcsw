#!/bin/bash
# 링크밴드 PC 소프트웨어 실행 (Tk GUI는 macOS Terminal에서 실행해야 Cursor 내부에서의 크래시를 피할 수 있음)
cd "$(dirname "$0")"
source .venv/bin/activate
python .vscode/main.py
