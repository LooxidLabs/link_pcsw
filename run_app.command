#!/bin/bash
# 링크밴드 PC 소프트웨어 실행 (Tk GUI는 macOS Terminal에서 실행해야 Cursor 내부에서의 크래시를 피할 수 있음)
cd "$(dirname "$0")"
source .venv/bin/activate

# 캐시 경로를 프로젝트 내부로 고정 (권한 이슈/Abort trap 완화)
mkdir -p ".cache/matplotlib" ".cache/fontconfig"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
export XDG_CACHE_HOME="$PWD/.cache"

python app/main.py
