# PPG_TEST

## Overview
링크밴드 2.0 버전을 테스트하기 위한 PC SW

## 실행 방법 (macOS)
Tkinter GUI는 **Cursor IDE 내부 터미널**에서 실행하면 macOS에서 크래시(SIGABRT)할 수 있습니다.  
반드시 **macOS Terminal.app**(또는 iTerm)에서 실행하세요.

- **방법 1**: Finder에서 `run_app.command` 더블클릭 (Terminal에서 자동 실행)
- **방법 2**: 터미널에서 직접 실행
  ```bash
  cd /path/to/link_pcsw
  source .venv/bin/activate
  python .vscode/main.py
  ```

## Update Notes
### 2025-05-14
1. 처음 커밋, MAC OS 개발
2. 링크밴드 BLE 통신 및 BLE 서비스 on/off
3. EEG/PPG/ACC 센서 데이터 그래프 출력
4. PPG 센서 RED/IR LEDs 지원
5. Raw 데이터 레코딩 기능

### 2025-05-16
1. PPG IR 센싱추가로 파일 레코딩 기능 추가
2. 샘플링 레이트 계산을 위한 코드 추가
3. 주석에 있는 이모티콘 삭제
