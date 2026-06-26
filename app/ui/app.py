"""Tkinter main window."""
# macOS: Tk GUI는 Cursor 내부 터미널에서 실행 시 크래시할 수 있음.
# Terminal.app에서 실행하거나 프로젝트 루트의 run_app.command 를 사용하세요.
import asyncio
import csv
import queue
import sys
import threading
import time
import tkinter as tk

import heartpy as hp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

matplotlib.use("TkAgg")

from app import constants, state
from app import version
from app.ble import client as ble_client
from app.ble import services as ble_services
from app.signal import filters as signal_filters
from app.ui.lead_off_panel import LeadOffPanel
from app.ui.eeg_gain_panel import EegGainPanel
from app import user_settings

toggle_accelerometer = ble_services.toggle_accelerometer
toggle_battery = ble_services.toggle_battery
toggle_eeg_write = ble_services.toggle_eeg_write
toggle_eeg_notify = ble_services.toggle_eeg_notify
toggle_ppg = ble_services.toggle_ppg

class App:
    def __init__(self, root):
        self.root = root
        root.title(version.window_title())

        # 프로토콜 핸들러 등록: X 클릭 시 on_closing 호출
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        saved = user_settings.load_settings()
        
        # Left Frame (Device selection and controls)
        left_frame = tk.Frame(root)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10, pady=10)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)

        left_upper = tk.Frame(left_frame)
        left_upper.grid(row=0, column=0, sticky="new")
        
        tk.Label(left_upper, text="BLE Device Selection:", font=("Arial", 14, "bold")).pack(pady=5)        

        # listbox와 스크롤바를 위한 프레임 생성 (고정 높이 — 로그 영역에 세로 공간 확보)
        listbox_frame = tk.Frame(left_upper)
        listbox_frame.pack(pady=5, fill=tk.X)

        self.listbox = tk.Listbox(listbox_frame, width=50, height=6)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
        # 세로 스크롤바 생성 및 listbox와 연동
        scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
                
        # Place Connect/Disconnect buttons on the same line
        btn_frame = tk.Frame(left_upper)
        btn_frame.pack(pady=5)
        self.connect_button = tk.Button(btn_frame, text="Connect", command=self.connect_device)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        self.disconnect_button = tk.Button(btn_frame, text="Disconnect", command=self.disconnect_device)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)        
        # self.rescan_button = tk.Button(left_frame, text="Rescan Devices", command=self.rescan_ble)
        # self.rescan_button.pack(pady=5)
        self.rescan_button = tk.Button(btn_frame, text="Rescan Devices", command=self.rescan_ble)
        self.rescan_button.pack(side=tk.LEFT, padx=5)
        
        # LXB 필터링 체크박스 추가
        filter_frame = tk.Frame(left_upper)
        filter_frame.pack(pady=5, fill=tk.X)
        filter_inner = tk.Frame(filter_frame)
        filter_inner.pack(anchor="center")
        self.lxb_filter_var = tk.BooleanVar(value=saved["lxb_filter_only"])
        self.lxb_filter_checkbox = tk.Checkbutton(
            filter_inner,
            text="Show LXB devices only",
            variable=self.lxb_filter_var,
            command=self.on_filter_changed,
        )
        self.lxb_filter_checkbox.pack(side=tk.LEFT, padx=(0, 12))

        self.eeg_raw_print_var = tk.BooleanVar(value=saved["eeg_raw_print"])
        state.eeg_raw_print_enabled = saved["eeg_raw_print"]
        self.eeg_raw_print_checkbox = tk.Checkbutton(
            filter_inner,
            text="EEG 로우데이터 출력",
            variable=self.eeg_raw_print_var,
            command=self.on_eeg_raw_print_toggle,
        )
        self.eeg_raw_print_checkbox.pack(side=tk.LEFT)

        self._auto_test_after_scan_connect = False
        self._auto_test_want_start_sensors = False
        self._auto_test_scan_busy = False
        auto_test_row = tk.Frame(left_upper)
        auto_test_row.pack(pady=5, fill=tk.X)
        auto_inner = tk.Frame(auto_test_row)
        auto_inner.pack(anchor="center")
        self.auto_test_var = tk.BooleanVar(value=saved["auto_test_mode"])
        tk.Checkbutton(
            auto_inner,
            text="자동 테스트 모드 (키보드 단축키)",
            variable=self.auto_test_var,
            command=self._on_auto_test_checkbox,
        ).pack()
        tk.Label(
            auto_inner,
            justify=tk.CENTER,
            text=(
                "C → 스캔 후 자동 연결 및 Start All Sensors\n"
                "D → 연결 종료\n"
                "(한글 입력 상태: ㅊ=C, ㅇ=D)\n"
                "(그래프 영역을 한 번 클릭한 뒤 키를 누르거나, 왼쪽 목록에 포커스를 주세요.)"
            ),
            fg="gray",
            font=("Arial", 9),
        ).pack()
        self.root.bind_all("<KeyPress>", self._auto_test_keypress_router)
        
        # Battery information label
        self.battery_info_label = tk.Label(left_upper, text="Battery Info: N/A")
        self.battery_info_label.pack(pady=5)
        
        # Service Control Frame (Buttons for each service)
        service_frame = tk.LabelFrame(
            left_upper,
            text="Service Control",
            font=("Arial", 14, "bold"),
            labelanchor="n",
            padx=5,
            pady=5,
        )
        service_frame.pack(pady=10, fill=tk.X)
        
        self.accelerometer_running = False
        self.battery_running = False
        self.eeg_write_running = False
        self.eeg_notify_running = False
        self.ppg_running = False
        
        # Service 버튼을 2열 그리드로 고정해 가로 폭을 동일하게 유지
        service_buttons_frame = tk.Frame(service_frame)
        service_buttons_frame.pack(fill=tk.X, padx=5, pady=2)
        service_buttons_frame.grid_columnconfigure(0, weight=1, uniform="svc")
        service_buttons_frame.grid_columnconfigure(1, weight=1, uniform="svc")

        self.battery_button = tk.Button(
            service_buttons_frame, text="Battery Start", command=lambda: toggle_battery(self)
        )
        self.battery_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)

        self.eeg_write_button = tk.Button(
            service_buttons_frame, text="EEG Write Start", command=lambda: toggle_eeg_write(self)
        )
        self.eeg_write_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

        self.accelerometer_button = tk.Button(
            service_buttons_frame, text="Accelerometer Start", command=lambda: toggle_accelerometer(self)
        )
        self.accelerometer_button.grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=2)
        self.eeg_notify_button = tk.Button(
            service_buttons_frame, text="EEG Notify Start", command=lambda: toggle_eeg_notify(self)
        )
        self.eeg_notify_button.grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=2)

        self.ppg_button = tk.Button(service_buttons_frame, text="PPG Start", command=lambda: toggle_ppg(self))
        self.ppg_button.grid(row=2, column=0, sticky="ew", padx=(0, 5), pady=2)

        self.bandpass_button = tk.Button(
            service_buttons_frame, text="Bandpass Filter: Off", command=self.toggle_bandpass
        )
        self.bandpass_button.grid(row=2, column=1, sticky="ew", padx=(5, 0), pady=2)

        self.notch_button = tk.Button(service_buttons_frame, text="Notch Filter: Off", command=self.toggle_notch)
        self.notch_button.grid(row=3, column=1, sticky="ew", padx=(5, 0), pady=2)

        # Start/Stop All Sensors 버튼을 좌우로 배치할 프레임 생성
        all_sensors_frame = tk.Frame(service_frame)
        all_sensors_frame.pack(fill=tk.X, padx=5, pady=8)
        self.start_all_btn = tk.Button(all_sensors_frame, text="Start All Sensors", command=self.start_all_sensors)
        self.start_all_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.stop_all_btn = tk.Button(all_sensors_frame, text="Stop All Sensors", command=self.stop_all_sensors)
        self.stop_all_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # --- 2. Record 버튼 추가 ---
        record_frame = tk.Frame(left_upper)
        record_frame.pack(pady=5)
        self.record_btn = tk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_btn.pack(side=tk.LEFT)
        # 레코딩 타이머 라벨 추가
        self.record_timer_label = tk.Label(record_frame, text="00:00", font=("Arial", 12))
        self.record_timer_label.pack(side=tk.LEFT, padx=10)
        self.rcd_status_label = tk.Label(record_frame, text="Recording: OFF", font=("Arial", 12))
        self.rcd_status_label.pack(side=tk.LEFT, padx=5)

        # BPM 표시 + 계산 활성화 체크박스
        bpm_frame = tk.Frame(left_upper)
        bpm_frame.pack(pady=5)
        self.bpm_label = tk.Label(bpm_frame, text="BPM: --", font=("Arial", 12))
        self.bpm_label.pack(side=tk.LEFT)
        self.bpm_calc_enabled_var = tk.BooleanVar(value=saved["bpm_calc_enabled"])  # 기본: 비활성화
        self.bpm_calc_checkbox = tk.Checkbutton(
            bpm_frame,
            text="BPM 계산",
            variable=self.bpm_calc_enabled_var,
            command=self.on_bpm_calc_toggle
        )
        self.bpm_calc_checkbox.pack(side=tk.LEFT, padx=8)

        # 메시지 로그 — 창 높이에 맞춰 남은 세로 공간을 모두 사용
        log_frame = tk.Frame(left_frame)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        
        tk.Label(log_frame, text="Message Log:").grid(row=0, column=0, sticky="w")

        log_body = tk.Frame(log_frame)
        log_body.grid(row=1, column=0, sticky="nsew")
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)
        
        self.message_listbox = tk.Listbox(log_body, width=60, height=8)
        self.message_listbox.grid(row=0, column=0, sticky="nsew")
        
        self.log_scrollbar = tk.Scrollbar(log_body, orient=tk.VERTICAL, command=self.message_listbox.yview)
        self.log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.message_listbox.config(yscrollcommand=self.log_scrollbar.set)
        
        # Right Frame (Lead-off + Real-time Plot Area)
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        plot_align = tk.Frame(right_frame)
        plot_align.pack(fill=tk.BOTH, expand=True)

        plot_column = tk.Frame(plot_align)
        plot_column.pack(anchor="n")

        eeg_top_row = tk.Frame(plot_column, width=constants.MAIN_PLOT_WIDTH_PX)
        eeg_top_row.pack(pady=(0, 8))

        self.lead_off_panel = LeadOffPanel(
            eeg_top_row, width=constants.EEG_LEAD_OFF_ROW_WIDTH_PX
        )
        self.lead_off_panel.pack(side=tk.LEFT, anchor="n")

        self.eeg_gain_panel = EegGainPanel(
            eeg_top_row,
            on_gain_change=self._on_eeg_gain_changed,
            width=constants.EEG_GAIN_PANEL_WIDTH_PX,
        )
        self.eeg_gain_panel.pack(side=tk.LEFT, anchor="n", padx=(constants.EEG_TOP_ROW_GAP_PX, 0))
        state.eeg_pga_gain = saved["eeg_pga_gain"]
        self.eeg_gain_panel.set_gain(state.eeg_pga_gain)
        self.refresh_eeg_gain_controls()

        plot_frame = tk.Frame(plot_column)
        plot_frame.pack(fill=tk.BOTH, expand=True)

        # Create 4 subplots: EEG Channel 1, EEG Channel 2, PPG Data, Accelerometer Data
        self.fig, self.axs = plt.subplots(
            4, 1, figsize=constants.MAIN_PLOT_FIGSIZE_INCH, dpi=constants.MAIN_PLOT_DPI
        )
        self.fig.tight_layout(pad=3.0)

        # EEG Channel 1 (subplot 0)
        self.line_eeg1, = self.axs[0].plot([], [])

        # EEG Channel 2 (subplot 1)
        self.line_eeg2, = self.axs[1].plot([], [])

        # PPG Data (subplot 2)
        self.line_ppg, = self.axs[2].plot([], [])

        # Accelerometer Data (subplot 3)
        self.line_acc_x, = self.axs[3].plot([], [], label="Acc X (mg)")
        self.line_acc_y, = self.axs[3].plot([], [], label="Acc Y (mg)")
        self.line_acc_z, = self.axs[3].plot([], [], label="Acc Z (mg)")
        self.axs[3].legend(
            loc="upper left",
            fontsize=6,
            markerscale=0.5,
            handlelength=1.0,
            borderpad=0.35,
            labelspacing=0.35,
            handletextpad=0.4,
        )

        # Sampling rate
        self.eeg_times = deque()
        self.ppg_times = deque()
        self.acc_times = deque()
        # self.root.after(1000, self.compute_sampling_rate)  # 주기적 실행 비활성화
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.config(width=constants.MAIN_PLOT_WIDTH_PX)
        canvas_widget.pack(fill=tk.Y, expand=True)
        # 그래프에 포커스가 있을 때는 Tk bind_all만으로 C/D가 안 들어올 수 있음 → matplotlib 키 이벤트로도 처리
        self.fig.canvas.mpl_connect("key_press_event", self._mpl_key_auto_test)

        self._apply_main_window_geometry()
        self._poll_ui_callbacks()
        self.update_plot()

    def _ui_alive(self) -> bool:
        if state.shutting_down:
            return False
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def _cancel_all_pending_after(self) -> None:
        """종료 시 예약된 after 콜백을 모두 취소해 invalid command 오류를 방지."""
        try:
            for job_id in self.root.tk.call("after", "info"):
                self.root.after_cancel(job_id)
        except tk.TclError:
            pass

    def _poll_ui_callbacks(self) -> None:
        """백그라운드 스레드가 큐에 넣은 Tk 콜백을 메인 스레드에서 실행."""
        if not self._ui_alive():
            return
        state.drain_ui_callbacks()
        if self._ui_alive():
            try:
                self.root.after(50, self._poll_ui_callbacks)
            except tk.TclError:
                pass

    def _apply_main_window_geometry(self):
        """시작 시 창이 화면 밖으로 잘리지 않도록 픽셀 크기·최소 크기·중앙 배치."""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        margin_x, margin_y = 48, 96  # 테두리·작업 표시줄 여유

        max_w = max(400, sw - margin_x)
        max_h = max(400, sh - margin_y)

        w = min(constants.MAIN_WINDOW_DEFAULT_W, max_w)
        h = min(constants.MAIN_WINDOW_DEFAULT_H, max_h)
        w = max(w, min(constants.MAIN_WINDOW_MIN_W, max_w))
        h = max(h, min(constants.MAIN_WINDOW_MIN_H, max_h))
        w = min(w, max_w)
        h = min(h, max_h)

        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        min_w = min(max_w, max(800, min(constants.MAIN_WINDOW_MIN_W, max_w)))
        min_h = min(max_h, max(560, min(constants.MAIN_WINDOW_MIN_H, max_h)))
        self.root.minsize(min_w, min_h)

    def _mpl_key_auto_test(self, event) -> None:
        """matplotlib 캔버스 포커스 상태에서의 C/D (Tk bind_all과 보완)"""
        if not getattr(self, "auto_test_var", None) or not self.auto_test_var.get():
            return
        key_raw = getattr(event, "key", "") or ""
        state.debug_log(f"mpl key_press_event: key={key_raw!r}")
        if "ctrl" in key_raw.lower():
            state.debug_log("mpl key 무시: Ctrl 조합")
            return
        k = self._normalize_auto_test_key(key_raw)
        if k == "c":
            self.root.after(0, self._auto_test_key_c_pipeline)
        elif k == "d":
            self.root.after(0, self._auto_test_key_d_disconnect)

    def _normalize_auto_test_key(self, key_raw: str):
        """영문/한글 입력 상태 모두에서 자동테스트 키를 동일 처리."""
        if not key_raw:
            return None
        # matplotlib key는 'ctrl+c' 같은 형태가 올 수 있어 마지막 토큰만 사용
        k = key_raw.split("+")[-1].strip().lower()
        mapping = {
            "c": "c",
            "d": "d",
            "ㅊ": "c",  # 한글 두벌식 C 위치
            "ㅇ": "d",  # 한글 두벌식 D 위치
        }
        return mapping.get(k)

    def _auto_test_keypress_router(self, event=None):
        """Tk 키 입력 라우터: c/d + 한글(ㅊ/ㅇ) 모두 지원."""
        if not self.auto_test_var.get():
            return
        key_char = getattr(event, "char", "") or ""
        key_sym = getattr(event, "keysym", "") or ""
        key_raw = key_char if key_char else key_sym
        k = self._normalize_auto_test_key(key_raw)
        if k == "c":
            return self._auto_test_key_c_pipeline(event)
        if k == "d":
            return self._auto_test_key_d_disconnect(event)
    
    # =====================================
    # Recording toggle method
    # =====================================
    def toggle_recording(self):
        if not state.recording:
            # 시작 시각
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            state.RAW_DIR.mkdir(exist_ok=True)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            state.eeg_file = open(state.RAW_DIR / f'eeg_{timestamp_str}.csv', 'w', newline='', encoding='utf-8')
            state.ppg_file = open(state.RAW_DIR / f'ppg_{timestamp_str}.csv', 'w', newline='', encoding='utf-8')
            state.acc_file = open(state.RAW_DIR / f'acc_{timestamp_str}.csv', 'w', newline='', encoding='utf-8')

            state.eeg_writer = csv.writer(state.eeg_file)
            state.ppg_writer = csv.writer(state.ppg_file)
            state.acc_writer = csv.writer(state.acc_file)
            state.eeg_writer.writerow(['timestamp', 'lead-off', 'ch1(µV)', 'ch2(µV)'])
            state.ppg_writer.writerow(['timestamp', 'ppg_red', 'ppg_ir'])
            state.acc_writer.writerow(['timestamp', 'acc_x_mg', 'acc_y_mg', 'acc_z_mg'])

            state.recording = True
            self.record_btn.config(text="Stop Recording")
            self.rcd_status_label.config(text="Recording: ON 🟢", font=("Arial", 12))
            self.record_start_time = time.time()  # ⏱️ 시작 시각 저장
            self.update_record_timer()            # ⏱️ 타이머 시작
            self.add_message(f"Recording started at {now_str}")
            self.add_message(f"Recording started → saved in raw_data/ (prefix: {timestamp_str})")
            self.add_message(f"EEG PGA Gain (locked): {state.eeg_pga_gain}")
            self.refresh_eeg_gain_controls()
        else:
            # 레코딩 종료 시각
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            state.recording = False            
            self.record_btn.config(text="Start Recording")
            self.rcd_status_label.config(text="Recording: OFF ⚪")
            self.record_timer_label.config(text="00:00")  # ⏹️ 타이머 초기화
            
            for f in (state.eeg_file, state.ppg_file, state.acc_file):
                if f:
                    f.close()
            state.eeg_file = state.ppg_file = state.acc_file = None
            state.eeg_writer = state.ppg_writer = state.acc_writer = None
            
            # 녹음 시간 계산
            if self.record_start_time is not None:
                duration = int(time.time() - self.record_start_time)
                minutes = duration // 60
                seconds = duration % 60
                self.add_message(f"⏱️ Total recording duration: {minutes}분 {seconds}초")
            self.record_start_time = None

            self.add_message(f"Recording stopped at {now_str}")
            self.refresh_eeg_gain_controls()            

    def update_record_timer(self):
        if not self._ui_alive():
            return
        if state.recording and self.record_start_time is not None:
            elapsed = int(time.time() - self.record_start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.record_timer_label.config(text=f"{minutes:02d}:{seconds:02d}")
            if self._ui_alive():
                try:
                    self.root.after(1000, self.update_record_timer)
                except tk.TclError:
                    pass



    def refresh_lead_off_indicators(self) -> None:
        if not hasattr(self, "lead_off_panel"):
            return
        if state.eeg_lead_off_raw is None:
            self.lead_off_panel.reset()
        else:
            self.lead_off_panel.update_electrodes(
                state.eeg_lead_off_electrodes, state.eeg_lead_off_raw
            )

    def refresh_eeg_gain_controls(self) -> None:
        """EEG Notify 또는 레코딩 중에는 Gain 변경 불가."""
        if not hasattr(self, "eeg_gain_panel"):
            return
        locked = self.eeg_notify_running or state.recording
        self.eeg_gain_panel.set_enabled(not locked)

    def _on_eeg_gain_changed(self, gain: int) -> None:
        if self.eeg_notify_running or state.recording:
            self.eeg_gain_panel.set_gain(state.eeg_pga_gain)
            return
        if gain not in constants.EEG_PGA_GAIN_OPTIONS:
            return
        if gain == state.eeg_pga_gain:
            return
        state.eeg_pga_gain = gain
        state.clear_eeg_data_buffer()
        self.eeg_times.clear()
        self.add_message(f"EEG PGA Gain → {gain} (µV 스케일 적용, EEG 버퍼 초기화)")
        self._save_user_settings()

    def _save_user_settings(self) -> None:
        if not user_settings.save_settings(user_settings.collect_from_app(self)):
            self.add_message("Warning: user_settings.json 저장 실패")

    def reset_lead_off_indicators(self) -> None:
        if not hasattr(self, "lead_off_panel"):
            return
        self.lead_off_panel.reset()

    def on_closing(self):
        self._save_user_settings()
        state.shutting_down = True
        state.disconnect_requested = True

        self._cancel_all_pending_after()

        try:
            self.root.unbind_all("<KeyPress>")
        except tk.TclError:
            pass

        if state.global_ble_client is not None and state.global_ble_loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    state.global_ble_client.disconnect(), state.global_ble_loop
                )
                future.result(timeout=3)
            except Exception as e:
                state.debug_log(f"on_closing: BLE disconnect — {e}")

        try:
            self.root.quit()
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

        state.global_main_root = None
        state.global_app = None
    
    def update_plot(self):
        if not self._ui_alive():
            return
        # EEG Channel 1 (subplot 0)
        # BLE 콜백이 다른 스레드에서 버퍼를 갱신하므로, 길이를 두 번 읽으면 t/y 불일치 발생 가능 → 한 번에 스냅샷
        eeg1_raw = np.asarray(state.data_buffer["eeg1"], dtype=float)
        n_eeg1 = eeg1_raw.size
        t = np.arange(n_eeg1, dtype=float) / constants.EEG_SAMPLE_RATE
        if n_eeg1 > constants.EEG_MAX_PLOT_POINTS:
            t = t[-constants.EEG_MAX_PLOT_POINTS:]
            eeg1 = eeg1_raw[-constants.EEG_MAX_PLOT_POINTS:]
        else:
            eeg1 = eeg1_raw
        if len(t) > 0:
            if state.filter_notch_enabled:
                eeg1 = signal_filters.apply_notch_filter(eeg1, constants.EEG_SAMPLE_RATE, 60.0,40.0)
            if state.filter_bandpass_enabled:
                eeg1 = signal_filters.apply_bandpass_filter(eeg1, constants.EEG_SAMPLE_RATE, 1.0, 50.0)
            self.line_eeg1.set_data(t, eeg1)
            self.axs[0].relim()
            self.axs[0].autoscale_view()
            self.axs[0].set_title("EEG Channel 1 " + ("(Filtered)" if (state.filter_notch_enabled or state.filter_bandpass_enabled) else ""))
        
        # EEG Channel 2 (subplot 1)
        eeg2_raw = np.asarray(state.data_buffer["eeg2"], dtype=float)
        n_eeg2 = eeg2_raw.size
        t2 = np.arange(n_eeg2, dtype=float) / constants.EEG_SAMPLE_RATE
        if n_eeg2 > constants.EEG_MAX_PLOT_POINTS:
            t2 = t2[-constants.EEG_MAX_PLOT_POINTS:]
            eeg2 = eeg2_raw[-constants.EEG_MAX_PLOT_POINTS:]
        else:
            eeg2 = eeg2_raw
        if len(t2) > 0:
            if state.filter_notch_enabled:
                eeg2 = signal_filters.apply_notch_filter(eeg2, constants.EEG_SAMPLE_RATE, 60.0,40.0)
            if state.filter_bandpass_enabled:
                eeg2 = signal_filters.apply_bandpass_filter(eeg2, constants.EEG_SAMPLE_RATE, 1.0, 50.0)
            self.line_eeg2.set_data(t2, eeg2)
            self.axs[1].relim()
            self.axs[1].autoscale_view()
            self.axs[1].set_title("EEG Channel 2 " + ("(Filtered)" if (state.filter_notch_enabled or state.filter_bandpass_enabled) else ""))
        
        # PPG Data (subplot 2)
        ppg_raw = np.asarray(state.data_buffer["ppg"], dtype=float)
        n_ppg = ppg_raw.size
        t_ppg = np.arange(n_ppg, dtype=float) / 50
        if n_ppg > constants.PPG_MAX_PLOT_POINTS:
            t_ppg = t_ppg[-constants.PPG_MAX_PLOT_POINTS:]
            ppg = ppg_raw[-constants.PPG_MAX_PLOT_POINTS:]
        else:
            ppg = ppg_raw
        if len(t_ppg) > 0:
            self.line_ppg.set_data(t_ppg, ppg)
            self.axs[2].relim()
            self.axs[2].autoscale_view()
            self.axs[2].set_title("PPG Data")
        
        # Accelerometer Data (subplot 3)
        acc_x_raw = np.asarray(state.data_buffer["acc_x"], dtype=float)
        acc_y_raw = np.asarray(state.data_buffer["acc_y"], dtype=float)
        acc_z_raw = np.asarray(state.data_buffer["acc_z"], dtype=float)
        n_acc = min(acc_x_raw.size, acc_y_raw.size, acc_z_raw.size)
        if n_acc == 0:
            t_acc = np.array([], dtype=float)
            acc_x = acc_y = acc_z = np.array([], dtype=float)
        else:
            acc_x_raw = acc_x_raw[:n_acc]
            acc_y_raw = acc_y_raw[:n_acc]
            acc_z_raw = acc_z_raw[:n_acc]
            t_acc = np.arange(n_acc, dtype=float) / constants.ACC_SAMPLE_RATE
            if n_acc > constants.ACC_MAX_PLOT_POINTS:
                t_acc = t_acc[-constants.ACC_MAX_PLOT_POINTS:]
                acc_x = acc_x_raw[-constants.ACC_MAX_PLOT_POINTS:]
                acc_y = acc_y_raw[-constants.ACC_MAX_PLOT_POINTS:]
                acc_z = acc_z_raw[-constants.ACC_MAX_PLOT_POINTS:]
            else:
                acc_x, acc_y, acc_z = acc_x_raw, acc_y_raw, acc_z_raw
        if len(t_acc) > 0:
            self.line_acc_x.set_data(t_acc, acc_x)
            self.line_acc_y.set_data(t_acc, acc_y)
            self.line_acc_z.set_data(t_acc, acc_z)
            self.axs[3].relim()
            self.axs[3].autoscale_view()
            self.axs[3].set_title("Accelerometer Data (mg)")
        
        self.refresh_lead_off_indicators()
        self.canvas.draw_idle()
        if self._ui_alive():
            try:
                self.root.after(200, self.update_plot)
            except tk.TclError:
                pass
    
    def _on_auto_test_checkbox(self):
        if not self.auto_test_var.get():
            state.debug_log("자동 테스트 체크 해제 → _auto_test_after_scan_connect 초기화")
            self._auto_test_after_scan_connect = False
        self._save_user_settings()

    def _auto_test_key_c_pipeline(self, event=None):
        state.debug_log(
            f"_auto_test_key_c_pipeline: auto_mode={self.auto_test_var.get()} "
            f"ble_client={'set' if state.global_ble_client else 'None'} "
            f"after_scan_flag={self._auto_test_after_scan_connect} scan_busy={self._auto_test_scan_busy}"
        )
        if not self.auto_test_var.get():
            state.debug_log("C 키 무시: 자동 테스트 모드 꺼짐")
            return
        if state.global_ble_client is not None:
            self.add_message("[Auto test] C: 이미 연결됨 → D 로 연결 종료 후 재시도")
            return "break"
        self.add_message("[Auto test] C: 스캔 → 목록 최우선(최신·강신호) 연결 → Start All Sensors")
        self._auto_test_after_scan_connect = True
        state.debug_log(f"C 파이프라인: _auto_test_after_scan_connect=True, rescan_ble 호출")
        self.rescan_ble()
        return "break"

    def _auto_test_key_d_disconnect(self, event=None):
        state.debug_log(f"_auto_test_key_d_disconnect: auto_mode={self.auto_test_var.get()} ble={state.global_ble_client is not None}")
        if not self.auto_test_var.get():
            return
        if state.global_ble_client is None:
            self.add_message("[Auto test] D: 연결된 디바이스 없음")
            return "break"
        self.add_message("[Auto test] D: 연결 종료")
        self.disconnect_device()
        return "break"

    def update_device_list(self, devices):
        """RSSI 높은 순(없으면 뒤)으로 정렬 후 최대 constants.MAX_SCAN_LIST_DEVICES개만 목록 표시."""

        def _sort_key(d):
            r = getattr(d, "rssi", None)
            # RSSI 알 수 없으면 -999로 두어 목록 후순위 (OS에 따라 없을 수 있음)
            return (r is not None, r if r is not None else -999)

        state.debug_log(
            f"update_device_list: 입력 {len(devices)}대, auto_mode={self.auto_test_var.get()} "
            f"after_scan_connect={self._auto_test_after_scan_connect}"
        )
        devices = sorted(devices, key=_sort_key, reverse=True)[:constants.MAX_SCAN_LIST_DEVICES]
        self.listbox.delete(0, tk.END)
        for dev in devices:
            self.listbox.insert(tk.END, f"{dev.name}: {dev.address}")
        self.add_message(f"{len(devices)} devices found (표시 최대 {constants.MAX_SCAN_LIST_DEVICES}대)")

        if self.auto_test_var.get() and self._auto_test_after_scan_connect:
            state.debug_log("자동 테스트: 스캔 완료 → 자동 연결 분기 진입")
            self._auto_test_after_scan_connect = False
            if state.global_ble_client is not None:
                self.add_message("[Auto test] 이미 연결됨 — 자동 연결 생략")
                state.debug_log("자동 연결 생략: state.global_ble_client 이미 존재")
                return
            if not devices:
                self.add_message("[Auto test] 디바이스 없음 — 연결 생략")
                state.debug_log("자동 연결 생략: 표시할 디바이스 0대")
                return
            dev0 = devices[0]
            state.debug_log(f"자동 연결 대상: {dev0.name!r} / {dev0.address!r} RSSI={getattr(dev0, 'rssi', None)!r}")
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self._auto_test_want_start_sensors = True
            self.connect_device_with_address(
                dev0.address, f"[Auto test] {dev0.name}: {dev0.address} 연결 중..."
            )
    
    def connect_device_with_address(self, device_address: str, log_message: str):
        state.debug_log(f"connect_device_with_address: {device_address!r} (ble={'set' if state.global_ble_client else 'None'})")
        if state.global_ble_client is not None:
            self.add_message("이미 연결됨")
            state.debug_log("connect_device_with_address: 중단 (이미 연결됨)")
            return
        threading.Thread(target=ble_client.ble_thread_main, args=(device_address,), daemon=True).start()
        self.add_message(log_message)

    def start_ble_scan_startup(self) -> None:
        """앱 기동 시 첫 스캔 (메인 스레드에서만 호출)"""
        self._auto_test_scan_busy = True
        self.add_message("Scan BLE devices...")
        lxb = bool(self.lxb_filter_var.get())
        state.debug_log(f"start_ble_scan_startup: lxb_only={lxb}")
        threading.Thread(target=ble_client._scan_ble_async_worker, args=(lxb,), daemon=True).start()
        self.root.after(50, self._poll_ble_scan_queue)

    def _poll_ble_scan_queue(self) -> None:
        if not self._ui_alive():
            return
        state.drain_ui_callbacks()
        try:
            kind, payload = state._ble_scan_queue.get_nowait()
        except queue.Empty:
            if self._ui_alive() and getattr(self, "_auto_test_scan_busy", False):
                try:
                    self.root.after(50, self._poll_ble_scan_queue)
                except tk.TclError:
                    pass
            return
        state.debug_log(f"_poll_ble_scan_queue: 수신 kind={kind!r}")
        self._auto_test_scan_busy = False
        if kind == "ok":
            self.update_device_list(payload)
        else:
            self.add_message(f"Scan failed: {payload}")
            state.debug_log(f"스캔 실패: {payload!r}")

    def connect_device(self):
        try:
            selected = self.listbox.get(self.listbox.curselection())
        except tk.TclError:
            self.add_message("Select a device")
            return
        # "Name: FC:08:70:EA:EC:98" → 첫 번째 ':' 기준으로만 분리해 주소 전체 추출
        device_address = selected.split(":", 1)[1].strip()
        self.connect_device_with_address(device_address, f"{selected} Connecting...")
    
    def disconnect_device(self):
        state.disconnect_requested = True
        self.add_message("Disconnect requested")
        self.accelerometer_running = False
        self.battery_running = False
        self.eeg_write_running = False
        self.eeg_notify_running = False
        self.ppg_running = False
        self.accelerometer_button.config(text="Accelerometer Start")
        self.battery_button.config(text="Battery Start")
        self.eeg_write_button.config(text="EEG Write Start")
        self.eeg_notify_button.config(text="EEG Notify Start")
        self.ppg_button.config(text="PPG Start")
        state.reset_eeg_lead_off()
        self.refresh_eeg_gain_controls()
    
    def rescan_ble(self):
        if getattr(self, "_auto_test_scan_busy", False):
            state.debug_log("rescan_ble: 이미 스캔 중 — 중복 요청 무시")
            return
        self.listbox.delete(0, tk.END)
        self._auto_test_scan_busy = True
        self.add_message("Scan BLE devices...")
        lxb = bool(self.lxb_filter_var.get())
        state.debug_log(f"rescan_ble: lxb_only={lxb}")
        threading.Thread(target=ble_client._scan_ble_async_worker, args=(lxb,), daemon=True).start()
        self.root.after(50, self._poll_ble_scan_queue)

    # 필터 토글 함수 (Notch, Bandpass)
    def toggle_notch(self):
        state.filter_notch_enabled = not state.filter_notch_enabled
        self.notch_button.config(text="Notch Filter: " + ("On" if state.filter_notch_enabled else "Off"))
    
    def toggle_bandpass(self):
        state.filter_bandpass_enabled = not state.filter_bandpass_enabled
        self.bandpass_button.config(text="Bandpass Filter: " + ("On" if state.filter_bandpass_enabled else "Off"))

    # LXB 필터 변경 시 자동으로 스캔 다시 실행
    def on_filter_changed(self):
        self.add_message(f"LXB filter {'enabled' if self.lxb_filter_var.get() else 'disabled'}")
        self._save_user_settings()
        self.rescan_ble()

    def on_bpm_calc_toggle(self):
        enabled = self.bpm_calc_enabled_var.get()
        if not enabled:
            self.bpm_label.config(text="BPM: --")
        self.add_message(f"BPM calculation {'enabled' if enabled else 'disabled'}")
        self._save_user_settings()

    def on_eeg_raw_print_toggle(self):
        state.eeg_raw_print_enabled = bool(self.eeg_raw_print_var.get())
        self.add_message(
            f"EEG raw data terminal output {'enabled' if state.eeg_raw_print_enabled else 'disabled'}"
        )
        self._save_user_settings()

    # 새로운 메시지를 추가하고 자동 스크롤하는 함수
    def add_message(self, message):
        self.message_listbox.insert(tk.END, message)
        # 새 메시지 추가 후 스크롤을 리스트박스의 마지막으로 이동
        self.message_listbox.yview_moveto(1)

    # FFT 창을 생성하고 실시간 업데이트하는 함수
    def show_fft(self):
        # 이미 FFT 창이 열려있으면 단순히 올라오게 함
        if hasattr(self, 'fft_window') and self.fft_window.winfo_exists():
            self.fft_window.lift()
            return
        
        self.fft_window = tk.Toplevel(self.root)
        self.fft_window.title("Real-time EEG FFT")
        
        # 2행 1열 subplot 구성
        self.fig_fft, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 10))
        self.fig_fft.tight_layout()
        
        # 초기에 빈 line 객체 생성 (업데이트 시 데이터를 변경)
        self.fft_line1, = self.ax1.plot([], [])
        self.fft_line2, = self.ax2.plot([], [])
        
        self.ax1.set_title("FFT of EEG Channel 1")
        self.ax1.set_xlabel("Frequency (Hz)")
        self.ax1.set_ylabel("Magnitude")
        self.ax2.set_title("FFT of EEG Channel 2")
        self.ax2.set_xlabel("Frequency (Hz)")
        self.ax2.set_ylabel("Magnitude")
        
        self.fft_canvas = FigureCanvasTkAgg(self.fig_fft, master=self.fft_window)
        self.fft_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 시작 시 FFT 그래프 업데이트 시작
        self.update_fft()
    
    def update_fft(self):
        if not self._ui_alive():
            return
        if not (hasattr(self, "fft_window") and self.fft_window.winfo_exists()):
            return
        # EEG1 데이터 FFT
        #data_eeg1 = np.array(state.data_buffer["eeg1"])
        #data_eeg2 = np.array(state.data_buffer["eeg2"])
        data_eeg1 = np.array(state.data_buffer["eeg1"][-1000:])
        data_eeg2 = np.array(state.data_buffer["eeg2"][-1000:])
        
        
        # 필터 적용 (노치, 밴드패스 선택에 따라)
        if state.filter_notch_enabled:
            if data_eeg1.size > 0:
                data_eeg1 = signal_filters.apply_notch_filter(data_eeg1, constants.SAMPLE_RATE, 60.0, 30.0)
            if data_eeg2.size > 0:
                data_eeg2 = signal_filters.apply_notch_filter(data_eeg2, constants.SAMPLE_RATE, 60.0, 30.0)
        if state.filter_bandpass_enabled:
            if data_eeg1.size > 0:
                data_eeg1 = signal_filters.apply_bandpass_filter(data_eeg1, constants.SAMPLE_RATE, 1.0, 50.0)
            if data_eeg2.size > 0:
                data_eeg2 = signal_filters.apply_bandpass_filter(data_eeg2, constants.SAMPLE_RATE, 1.0, 50.0)
        
        # EEG1 FFT 계산 및 업데이트
        if data_eeg1.size > 0:
            n1 = len(data_eeg1)
            fft_values1 = np.fft.rfft(data_eeg1)
            fft_freqs1 = np.fft.rfftfreq(n1, d=1.0/constants.SAMPLE_RATE)
            magnitude1 = np.abs(fft_values1)
            self.fft_line1.set_data(fft_freqs1, magnitude1)
            self.ax1.relim()
            self.ax1.autoscale_view()
        else:
            self.fft_line1.set_data([], [])
        
        # EEG2 FFT 계산 및 업데이트
        if data_eeg2.size > 0:
            n2 = len(data_eeg2)
            fft_values2 = np.fft.rfft(data_eeg2)
            fft_freqs2 = np.fft.rfftfreq(n2, d=1.0/constants.SAMPLE_RATE)
            magnitude2 = np.abs(fft_values2)
            self.fft_line2.set_data(fft_freqs2, magnitude2)
            self.ax2.relim()
            self.ax2.autoscale_view()
        else:
            self.fft_line2.set_data([], [])
        
        self.fft_canvas.draw_idle()
        # FFT 창이 열려 있다면 500ms 후에 다시 업데이트
        if self._ui_alive() and hasattr(self, "fft_window") and self.fft_window.winfo_exists():
            try:
                self.fft_window.after(500, self.update_fft)
            except tk.TclError:
                pass

    def update_bpm(self):
        # print("update_bpm called")
        if not self._ui_alive():
            return
        if state.disconnect_requested or not self.ppg_running:
            state.data_buffer["ppg"].clear()
            return

        if not self.bpm_calc_enabled_var.get():
            self.bpm_label.config(text="BPM: --")
            if self._ui_alive() and not state.disconnect_requested:
                try:
                    self.root.after(1000, self.update_bpm)
                except tk.TclError:
                    pass
            return
        
        try:
            recent_ppg = np.array(state.data_buffer["ppg"][-500:])  # 10초치 (50Hz)
            recent_ppg_ir  = np.array(state.data_buffer["ppg_ir"][-500:])
            # print("recent_ppg length:", len(recent_ppg))
            if len(recent_ppg) >= 250 and len(recent_ppg_ir) >= 250:  # 최소한 5초 이상 확보
                # wd, m = hp.process(recent_ppg, sample_rate=constants.PPG_SAMPLE_RATE)
                # print("wd:", wd)
                # 1️⃣ 필터 적용 (0.7 ~ 3.5Hz → 약 42 ~ 210 bpm)
                filtered_ppg = hp.filter_signal(recent_ppg, cutoff=[0.7, 3.5], sample_rate=constants.PPG_SAMPLE_RATE, order=3, filtertype='bandpass')
                wd, m = hp.process(filtered_ppg, sample_rate=constants.PPG_SAMPLE_RATE)
                # wd, m = hp.process(filtered_ppg, sample_rate=50, peakwindow=0.5, ma_perc=15)
                bpm_val = m['bpm']
                sdnn_val = m['sdnn']
                ibi_val = m['ibi']
                self.bpm_label.config(text=f"BPM: {bpm_val:.1f}")
                spo2 = signal_filters.calculate_spo2(recent_ppg, recent_ppg_ir)
                # print(f"BPM: {bpm_val:.1f}, SDNN: {sdnn_val:.1f} ms, IBI: {ibi_val:.1f} ms, SPO2: {spo2:.1f}%")
                # self.add_message(f"BPM: {bpm_val:.1f}, SDNN: {sdnn_val:.1f} ms, IBI: {ibi_val:.1f} ms, SPO2: {spo2:.1f}%")
                # print(wd['RR_list'])
                
            else:
                self.bpm_label.config(text="BPM: --")
                # print("BPM:--")
        except Exception as e:
            # 노이즈 등으로 분석 실패할 경우
            self.bpm_label.config(text="BPM: --")
            print("Error in update_bpm:", e)
            # print("BPM:xx")
        finally:
            if self._ui_alive() and not state.disconnect_requested:
                try:
                    self.root.after(1000, self.update_bpm)  # 1초마다 반복
                except tk.TclError:
                    pass
    
    # 1초마다 EEG, PPG, ACC 샘플링 레이트 카운트 리포트
    def compute_sampling_rate(self):
        now = time.time()
        # EEG: 10초 이전 데이터는 제거
        while self.eeg_times and self.eeg_times[0] < now - 10:
            self.eeg_times.popleft()
        # PPG
        while self.ppg_times and self.ppg_times[0] < now - 10:
            self.ppg_times.popleft()
        # ACC
        while self.acc_times and self.acc_times[0] < now - 10:
            self.acc_times.popleft()

        # 윈도우 내 샘플 개수 / 10초 → Hz
        eeg_rate = len(self.eeg_times) / 10.0
        ppg_rate = len(self.ppg_times) / 10.0
        acc_rate = len(self.acc_times) / 10.0

        # 로그창에도 출력
        self.add_message(
            f"[Sampling Rate] EEG: {eeg_rate:.1f} Hz, "
            f"PPG: {ppg_rate:.1f} Hz, "
            f"ACC: {acc_rate:.1f} Hz"
        )

        # 1초 후에 다시 계산
        # self.root.after(1000, self.compute_sampling_rate)
        
    # Service toggle buttons (called by UI)
    def toggle_accelerometer_service(self):
        toggle_accelerometer(self)
    def toggle_battery_service(self):
        toggle_battery(self)
    def toggle_eeg_write_service(self):
        toggle_eeg_write(self)
    def toggle_eeg_notify_service(self):
        toggle_eeg_notify(self)
    def toggle_ppg_service(self):
        toggle_ppg(self)

    def start_all_sensors(self):
        # 이미 켜진 센서는 토글하지 않음 (반복 클릭 시 꺼지는 현상 방지)
        if not self.accelerometer_running:
            self.add_message("[All Sensors] Accelerometer 시작...")
            toggle_accelerometer(self)
        self.root.after(200, lambda: (
            [self.add_message("[All Sensors] PPG 시작..."), toggle_ppg(self)]
            if not self.ppg_running else None
        ))
        self.root.after(200, lambda: (
            [self.add_message("[All Sensors] EEG Notify 시작..."), toggle_eeg_notify(self)]
            if not self.eeg_notify_running else None
        ))

    def stop_all_sensors(self):
        # 이미 꺼진 센서는 토글하지 않음 (반복 클릭 시 다시 켜지는 현상 방지)
        if self.accelerometer_running:
            self.add_message("[All Sensors] Accelerometer 정지...")
            toggle_accelerometer(self)
        self.root.after(200, lambda: (
            [self.add_message("[All Sensors] PPG 정지..."), toggle_ppg(self)]
            if self.ppg_running else None
        ))
        self.root.after(200, lambda: (
            [self.add_message("[All Sensors] EEG Notify 정지..."), toggle_eeg_notify(self)]
            if self.eeg_notify_running else None
        ))
