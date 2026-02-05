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
