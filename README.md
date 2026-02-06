# PPG_TEST

## Overview
링크밴드 2.0 버전을 테스트하기 위한 PC SW. **Windows / macOS** 모두 실행 가능 (Python 3.8+, 동일 코드베이스).

## Windows: 설치 절차 (최초 1회)

`run_app.bat`을 실행하기 **전에** 아래를 한 번만 진행하면 됩니다.

1. **Python 3.8 이상 설치**
   - [python.org/downloads](https://www.python.org/downloads/) 에서 설치 시 **"Add Python to PATH"** 체크.
   - 또는 Microsoft Store에서 "Python 3.12" 등 설치.

2. **명령 프롬프트(cmd)** 를 열고 프로젝트 폴더로 이동
   ```cmd
   cd C:\경로\to\link_pcsw
   ```

3. **가상환경 생성**
   ```cmd
   python -m venv .venv
   ```

4. **가상환경 활성화 후 패키지 설치**
   ```cmd
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **(선택) BLE(블루투스) 사용 시**
   - Windows 10 **버전 16299**(Fall Creators Update) 이상.
   - 설정 → Bluetooth 및 장치에서 **블루투스** 켜기.

이후부터는 **`run_app.bat`** 더블클릭만 하면 됩니다.

---

## 실행 방법

### Windows
- **방법 1**: `run_app.bat` 더블클릭 (위 설치 절차 완료 후)
- **방법 2**: 명령 프롬프트에서 직접 실행
  ```cmd
  cd C:\path\to\link_pcsw
  .venv\Scripts\activate
  python .vscode\main.py
  ```

### macOS
Tkinter GUI는 **Cursor IDE 내부 터미널**에서 실행하면 macOS에서 크래시(SIGABRT)할 수 있으므로, **Terminal.app**에서 실행하세요.

- **방법 1**: Finder에서 `run_app.command` 더블클릭
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

### 2026-02-06
1. 맥OS Cursor 내부 터미널 실행 시 Tk 크래시 대응 — `run_app.command` 추가
2. 윈도우 `run_app.bat` 추가
3. `requirements.txt` 정리 — 실제 사용 패키지만 유지(bleak, numpy, scipy, matplotlib, heartpy), setuptools 추가(Windows에서 heartpy `pkg_resources` 오류 방지), 표준 라이브러리·pandas 제거
4. `main.py`에서 `"BLE connection error:{e}"` → `f"BLE connection error: {e}"` 로 수정해 예외 메시지가 로그에 출력되도록 함
5. 디바이스 선택 시 `split(":")[-1]`로 인해 주소 일부만 전달되던 문제 수정 — `split(":", 1)[1].strip()`으로 전체 주소 사용
6. 시작/종료 반복 클릭 시 토글로 인해 한 번 켜짐/한 번 꺼짐이 반복되던 현상 수정