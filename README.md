# PPG_TEST

## Overview
링크밴드 2.0 버전을 테스트하기 위한 PC SW (**v2.3.3**). **Windows / macOS** 모두 실행 가능 (Python 3.8+, 동일 코드베이스).

애플리케이션 코드는 `app/` 패키지로 구성되어 있으며, 엔트리 포인트는 `app/main.py`입니다. 실행 시 **창 제목**에 `LINKBAND PC SW v2.3.3` 형태로 버전이 표시됩니다. 버전 번호는 `app/version.py`의 `APP_VERSION`에서 관리합니다.

사용자 UI 설정(체크박스, EEG PGA Gain)은 프로젝트 루트(또는 exe 옆)의 **`user_settings.json`**에 저장되며, 다음 실행 시 복원됩니다. 파일이 없으면 기본값으로 시작합니다.

## 프로젝트 구조

```
link_pcsw/
  app/
    main.py              # 앱 엔트리 (Tk mainloop)
    version.py           # 앱 이름·버전 (APP_VERSION=2.3.3)
    constants.py         # UUID, 샘플레이트, 창/플롯 크기 상수
    state.py             # 런타임 상태, UI 콜백 큐
    user_settings.py     # user_settings.json 로드/저장
    ble/                 # BLE 스캔·연결·서비스 토글·notify 콜백
    signal/              # 필터, EEG lead-off, µV(eeg_scale), ACC mg(acc_scale)
    ui/                  # Tkinter GUI, lead-off·PGA gain 패널
  docs/
    eeg-raw-data-format.md   # EEG 패킷·lead-off 비트맵 문서
  run_app.bat            # Windows 실행
  run_app.command        # macOS 실행
  build_windows_release.bat
  raw_data/              # 레코딩 CSV (실행 시 생성)
  user_settings.json     # 사용자 UI 설정 (실행·변경 시 생성, Git 제외)
```

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
  python app\main.py
  ```

### macOS
Tkinter GUI는 **Cursor IDE 내부 터미널**에서 실행하면 macOS에서 크래시(SIGABRT)할 수 있으므로, **Terminal.app**에서 실행하세요.

- **방법 1**: Finder에서 `run_app.command` 더블클릭
- **방법 2**: 터미널에서 직접 실행
  ```bash
  cd /path/to/link_pcsw
  source .venv/bin/activate
  python app/main.py
  ```

## Windows 배포판 빌드 (Win10/11)

Python이 설치된 Windows에서 아래 배치 파일을 실행하면, 배포 가능한 실행 폴더를 생성합니다.

```cmd
build_windows_release.bat
```

생성 결과:

- `release\windows\LINKBAND_PC_SW\` : 실행 파일 및 런타임 파일
- `release\windows\run_app.bat` : 최종 사용자 실행용 배치 파일

배포 시에는 `release\windows` 폴더 전체를 전달하면 됩니다.

## 자동 테스트 모드

자동 테스트 모드를 체크하면 키보드로 테스트 플로우를 진행할 수 있습니다.

- `C` (또는 한글 입력 상태 `ㅊ`): 스캔 → 우선순위 디바이스 자동 연결 → `Start All Sensors`
- `D` (또는 한글 입력 상태 `ㅇ`): 연결 종료

동작 규칙:

- 스캔 결과는 최대 5대(`MAX_SCAN_LIST_DEVICES`)만 리스트에 표시됩니다.
- 자동 연결 대상은 스캔 결과를 RSSI 기준으로 정렬한 뒤 첫 번째 디바이스입니다.
- 자동 모드에서 연결 성공 시 `Start All Sensors`가 자동 실행됩니다.

디버그 로그:

- 자동 테스트 관련 디버그는 GUI Message Log가 아니라 터미널(stderr)로 출력됩니다.
- 끄려면 환경변수 `LINK_PCSW_DEBUG=0`으로 실행하세요.

## UI 기능 요약

### Service Control
- Battery / Accelerometer / PPG / EEG Write / EEG Notify / Bandpass / Notch / Start·Stop All Sensors
- 버튼은 **2열 그리드**로 배치되어 가로 폭을 균일하게 유지합니다.
- BLE **연결 직후** Device Information **Firmware Revision (0x2A26)** GATT Read → Message Log 출력 (없으면 “펌웨어 버전 정보 없음”)

### EEG Lead-Off · PGA Gain
- **Lead-Off**: EEG Notify 수신 시 **CH1 + / CH1 − / CH2 + / CH2 −** 4개 LED (그래프 위, Lead-Off 패널)
- **PGA Gain**: **8 / 12** 선택 — 디바이스 Gain에 맞춰 µV 변환 (`app/signal/eeg_scale.py`)
- Lead-Off와 Gain 패널은 **그래프 상단 한 줄(좌우 배치)**
- Gain 변경: EEG Notify·레코딩 **중에는 불가**
- **초록**: 전극 접촉 · **빨강**: lead-off · **회색**: 데이터 없음
- **Lead-Off raw**: 4비트 값을 **2진수·16진수**로 패널 하단에 표시 (예: `BIN: 0b0000   HEX: 0x00`)
- 패킷 포맷: [`docs/eeg-raw-data-format.md`](docs/eeg-raw-data-format.md)

### 기타
- **Show LXB devices only**: LXB 이름 디바이스만 스캔 목록에 표시 (기본: 켜짐, **재실행 시 복원**)
- **EEG 로우데이터 출력**: 체크 시 EEG raw 패킷/샘플을 터미널에 출력 (기본: 꺼짐, **재실행 시 복원**)
- **자동 테스트 모드** / **BPM 계산**: 마지막 설정 **재실행 시 복원**
- **Message Log**: 왼쪽 하단, 창 높이에 맞춰 확장되는 스크롤 로그

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

### 2026-04-14
1. PPG 기반 BPM 계산을 사용자가 켜고 끌 수 있도록 **「BPM 계산」체크박스** 추가 (기본값: 꺼짐). BPM 라벨 옆에 배치.
2. `run_app.bat` 정상 종료 후 CMD가 멈추지 않도록 **마지막 `pause` 제거** (오류 시 `pause`는 유지).
3. Windows 10/11 **배포판 빌드** — `build_windows_release.bat` 추가(PyInstaller onedir), 산출물 `release\windows\` 및 사용자용 `run_app.bat` 생성.
4. 배포 exe에서 `raw_data` 저장 경로가 exe 폴더 기준이 되도록 **`sys.frozen` 분기**로 `RAW_DIR` 보정.
5. 시작 시 UI가 잘리지 않도록 **기본 창 크기(1536×864 논리 픽셀)·최소 크기·화면 맞춤·중앙 배치** 적용, 메인 그래프 **8×8 인치 @100dpi**로 조정.
6. 실시간 플롯에서 BLE 스레드와 경쟁할 때 `t`와 신호 길이가 어긋나던 문제 수정 — **`update_plot`에서 버퍼 스냅샷** 후 축 생성, 가속도계는 x/y/z **최소 길이**로 정렬.

### 2026-05-09
1. 자동 테스트 모드 체크박스 추가 및 단축키 기반 테스트 플로우 구현(`C`: 스캔→자동연결→Start All Sensors, `D`: 연결 종료).
2. 한글 입력 상태에서도 자동 테스트 키가 동작하도록 키 매핑 추가(`ㅊ`=C, `ㅇ`=D).
3. 스캔 결과 처리 안정화: 스캔 워커 스레드와 GUI 스레드를 큐로 분리하고, 스캔 중복 실행 방지 로직 적용.
4. 자동 테스트 디버그 로그를 GUI Message Log가 아닌 터미널(stderr) 출력으로 변경.
5. 연결 직후 표준 Battery Level(0x2A19)를 즉시 읽어 배터리 라벨을 갱신하도록 개선.

### 2026-06-18
1. **코드 리팩토링** — 단일 `main.py`를 `app/` 패키지로 분리 (`ble/`, `ui/`, `signal/`, `state.py`, `constants.py`). 엔트리는 `app/main.py`, `.vscode/main.py`는 호환 래퍼.
2. **EEG Lead-Off UI** — 패킷 lead-off 바이트를 4전극(CH1/CH2 P·N) LED로 표시. 그래프 상단, 패널 너비 600px.
3. **UI 레이아웃** — Service Control 2열·`LabelFrame` 테두리, Message Log 세로 확장, Lead-Off 패널을 왼쪽에서 그래프 영역으로 이동.
4. **EEG 로우데이터 출력** 체크박스 추가 (LXB 필터 옆, 기본 꺼짐). BLE 스레드 안전을 위해 `BooleanVar` 대신 플래그 사용.
5. **스레드 안전 UI** — BLE/백그라운드 스레드에서 Tk `after()` 직접 호출 제거, `_ui_callback_queue` + 메인 스레드 폴링으로 변경 (`Stop All Sensors` 시 GIL 크래시 방지).
6. **종료 처리** — 창 닫기 시 예약된 `after` 콜백 취소, `shutting_down` 가드로 `invalid command name` 오류 완화.
7. **문서** — [`docs/eeg-raw-data-format.md`](docs/eeg-raw-data-format.md) 추가 (179B 패킷, lead-off 비트맵, µV 변환).
8. **실행 스크립트** — `run_app.bat`, `run_app.command`, `build_windows_release.bat` 엔트리를 `app/main.py` 기준으로 정리. macOS `run_app.command`에 matplotlib/fontconfig 캐시 경로 고정.
9. **소프트웨어 버전 v2.0** — `app/version.py` 추가, 창 제목에 `LINKBAND PC SW v2.0` 표시.

### 2026-06-19 (v2.1)
1. **EEG PGA Gain 선택** — Gain 8/12 UI, `raw_to_uv()` 분리(`app/signal/eeg_scale.py`). EEG Notify·레코딩 중 변경 불가.
2. **Lead-Off + Gain 패널** — 그래프 상단 **좌우 배치** (plot 너비 800px 기준).
3. **사용자 설정 저장** — `user_settings.json`으로 LXB 필터, 로우데이터 출력, 자동 테스트, BPM 계산, PGA Gain **재실행 시 복원**. 파일 없으면 기본값.
4. **소프트웨어 버전 v2.1** — 창 제목 `LINKBAND PC SW v2.1`.

### 2026-06-20 (v2.2)
1. **펌웨어 버전 표시** — 연결 시 GATT **Firmware Revision String (0x2A26)** 읽어 Message Log에 출력. characteristic 없음·읽기 실패·빈 값이면 “펌웨어 버전 정보 없음”.
2. **소프트웨어 버전 v2.2** — 창 제목 `LINKBAND PC SW v2.2`.

### 2026-06-20 (v2.3)
1. **레코딩 CSV UTF-8** — `raw_data` EEG/PPG/ACC CSV 저장 시 `encoding='utf-8'` 지정. Windows(cp949)에서 `ch1(µV)` 헤더 기록 시 `UnicodeEncodeError` 방지.
2. **소프트웨어 버전 v2.3** — 창 제목 `LINKBAND PC SW v2.3`.

### 2026-06-26 (v2.3.1)
1. **가속도 파싱 수정** — LIS3DH int16 little-endian 6바이트 샘플 → `>> 4` → **mg** (`app/signal/acc_scale.py`). CSV 헤더 `acc_x_mg` / `acc_y_mg` / `acc_z_mg`. ODR **25 Hz** (`ACC_SAMPLE_RATE`).
2. **그래프 범례** — EEG/PPG 범례 제거(제목만), ACC 범례 `upper right` 고정.
3. **소프트웨어 버전 v2.3.1** — 창 제목 `LINKBAND PC SW v2.3.1`.

### 2026-06-26 (v2.3.2)
1. **ACC 그래프 범례** — 좌상단(`upper left`) 고정, 글자·마커 크기 약 절반.
2. **소프트웨어 버전 v2.3.2** — 창 제목 `LINKBAND PC SW v2.3.2`.

### 2026-06-26 (v2.3.3)
1. **Lead-Off 패널** — 4비트 lead-off raw 값을 **2진수·16진수**로 LED 아래 표시.
2. **소프트웨어 버전 v2.3.3** — 창 제목 `LINKBAND PC SW v2.3.3`.