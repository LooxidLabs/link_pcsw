"""Mutable runtime state and UI-thread helpers."""
import os
import queue
import sys
import time
import tkinter as tk
from pathlib import Path

data_buffer = {
    "eeg1": [],
    "eeg2": [],
    "ppg": [],
    "ppg_ir": [],
    "acc_x": [],
    "acc_y": [],
    "acc_z": [],
}

filter_notch_enabled = False
filter_bandpass_enabled = False
disconnect_requested = False
shutting_down = False
# BLE 콜백 스레드에서 읽음 — Tk BooleanVar.get()은 메인 스레드 전용이라 별도 플래그 사용
eeg_raw_print_enabled = False

# Global BLE client and event loop for service control
global_ble_client = None
global_ble_loop = None

# Global Tkinter root and App instance for UI updates
global_main_root = None
global_app = None

# Queue for passing characteristic UUID (not used in this version)
selected_uuid_queue = queue.Queue()

# 블루투스 스캔: 워커 스레드 → 큐 → 메인 스레드만 Tk/GUI 업데이트
_ble_scan_queue: queue.Queue = queue.Queue()

# BLE/백그라운드 스레드 → 메인 스레드 Tk 콜백 (root.after()는 메인 스레드에서만 호출)
_ui_callback_queue: queue.Queue = queue.Queue()

# 레코딩 관련 전역 변수 (채널별)
recording = False
eeg_file = None
ppg_file = None
acc_file = None
eeg_writer = None
ppg_writer = None
acc_writer = None

# EEG lead-off (최신 패킷 기준, BLE 콜백에서 갱신)
eeg_lead_off_raw: int | None = None
eeg_lead_off_electrodes: dict[str, bool] = {}

# 실행 위치 기준 raw_data 폴더 경로
# - python 실행: 프로젝트 루트 기준
# - 배포 exe 실행(PyInstaller): exe 파일 위치 기준
APP_BASE_DIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
RAW_DIR = APP_BASE_DIR / "raw_data"


def _debug_enabled() -> bool:
    return os.environ.get("LINK_PCSW_DEBUG", "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
        "NO",
    )


def debug_log(msg: str) -> None:
    if not _debug_enabled():
        return
    line = f"[DEBUG {time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)


def _run_on_ui(callback) -> None:
    """BLE/백그라운드 스레드에서 Tk 위젯 갱신 시 큐에 넣고 메인 스레드가 실행."""
    if shutting_down:
        return
    try:
        _ui_callback_queue.put_nowait(callback)
    except queue.Full:
        pass


def drain_ui_callbacks() -> None:
    """메인 스레드에서만 호출 — 큐에 쌓인 UI 콜백 실행."""
    while True:
        try:
            callback = _ui_callback_queue.get_nowait()
        except queue.Empty:
            break
        if shutting_down:
            continue
        try:
            callback()
        except tk.TclError:
            pass
        except Exception as e:
            debug_log(f"UI callback error: {type(e).__name__}: {e}")


def _run_on_ui_after(delay_ms: int, callback) -> None:
    """백그라운드에서 지연 Tk 콜백 예약 — after()는 메인 스레드에서 호출."""
    def schedule() -> None:
        if shutting_down or global_main_root is None:
            return
        try:
            global_main_root.after(delay_ms, callback)
        except tk.TclError:
            pass

    _run_on_ui(schedule)


def clear_data_buffer() -> None:
    for key in data_buffer:
        data_buffer[key].clear()


def update_eeg_lead_off(lead_off_raw: int) -> None:
    """BLE 콜백에서 lead-off 상태만 갱신 (UI는 update_plot에서 메인 스레드 갱신)."""
    from app.signal.lead_off import decode_electrodes

    global eeg_lead_off_raw, eeg_lead_off_electrodes
    eeg_lead_off_raw = lead_off_raw & 0x0F
    eeg_lead_off_electrodes = decode_electrodes(eeg_lead_off_raw)


def reset_eeg_lead_off() -> None:
    global eeg_lead_off_raw, eeg_lead_off_electrodes
    eeg_lead_off_raw = None
    eeg_lead_off_electrodes = {}
    if global_app is not None and not shutting_down:
        global_app.reset_lead_off_indicators()
