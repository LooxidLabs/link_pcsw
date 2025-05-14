import asyncio
import threading
import queue
import sys
import csv
import time
import os
import tkinter as tk
import numpy as np
import heartpy as hp

from pathlib import Path

# matplotlib 백엔드를 TkAgg로 설정 (Tkinter와 호환)
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from scipy.signal import iirnotch, butter, lfilter, filtfilt
from bleak import BleakScanner, BleakClient

# =====================================
# Fixed Service/Characteristic UUIDs
# =====================================
ACCELEROMETER_SERVICE_UUID = "75c276c3-8f97-20bc-a143-b354244886d4"
ACCELEROMETER_CHAR_UUID    = "d3d46a35-4394-e9aa-5a43-e7921120aaed"

BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_CHAR_UUID    = "00002a19-0000-1000-8000-00805f9b34fb"

EEG_WRITE_SERVICE_UUID = "df7b5d95-3afe-00a1-084c-b50895ef4f95"
EEG_WRITE_CHAR_UUID    = "0065cacb-9e52-21bf-a849-99a80d83830e"

EEG_NOTIFY_SERVICE_UUID = "df7b5d95-3afe-00a1-084c-b50895ef4f95"
EEG_NOTIFY_CHAR_UUID    = "00ab4d15-66b4-0d8a-824f-8d6f8966c6e5"

PPG_SERVICE_UUID = "1cc50ec0-6967-9d84-a243-c2267f924d1f"
PPG_CHAR_UUID    = "6c739642-23ba-818b-2045-bfe8970263f6"

# =====================================
# Global Variables and Data Buffer
# =====================================
SAMPLE_RATE = 250  # Hz
EEG_SAMPLE_RATE = 250
PPG_SAMPLE_RATE = 50
ACC_SAMPLE_RATE = 30

# 타임스탬프 계산을 위한, 패킷 스트리밍 개수
EEG_TIME_DIVISION = 25
PPG_TIME_DIVISION = 50
ACC_TIME_DIVISION = 30

data_buffer = {
    "eeg1": [],
    "eeg2": [],
    "ppg": [],
    "ppg_ir": [],
    "acc_x": [],
    "acc_y": [],
    "acc_z": []
}

filter_notch_enabled = False
filter_bandpass_enabled = False
disconnect_requested = False

# Global BLE client and event loop for service control
global_ble_client = None
global_ble_loop = None

# Global Tkinter root and App instance for UI updates
global_main_root = None
global_app = None

# Queue for passing characteristic UUID (not used in this version)
selected_uuid_queue = queue.Queue()

# Maximum number of data points to display on graph
MAX_PLOT_POINTS = 200
ACC_MAX_PLOT_POINTS = 240
PPG_MAX_PLOT_POINTS = 240
EEG_MAX_PLOT_POINTS = 1250

# 레코딩 관련 전역 변수 (채널별) 추가 ---
recording = False
eeg_file = None
ppg_file = None
acc_file = None
eeg_writer = None
ppg_writer = None
acc_writer = None

# 실행 파일(스크립트) 기준 raw_data 폴더 경로
RAW_DIR = Path(__file__).parent / 'raw_data'


# =====================================
# data_buffer clear Functions
# =====================================
def clear_data_buffer():
    for key in data_buffer:
        data_buffer[key].clear()

# =====================================
# Filter Functions
# =====================================
#def apply_notch_filter(data, sample_rate, freq, Q):
#    b, a = iirnotch(freq, Q, sample_rate)
#    return lfilter(b, a, data)

def apply_notch_filter(data, sample_rate, freq, Q):
    b, a = iirnotch(freq, Q, sample_rate)
    # filtfilt를 사용하여 양방향 필터링 적용 (위상 왜곡 및 과도 응답 제거)
    return filtfilt(b, a, data)

#def apply_bandpass_filter(data, sample_rate, low, high, order=4):
#    nyquist = 0.5 * sample_rate
#    low /= nyquist
#    high /= nyquist
#    b, a = butter(order, [low, high], btype='band')
#    return lfilter(b, a, data)

def apply_bandpass_filter(data, sample_rate, low, high, order=4):
    nyquist = 0.5 * sample_rate
    low_norm = low / nyquist
    high_norm = high / nyquist
    b, a = butter(order, [low_norm, high_norm], btype='band')
    return filtfilt(b, a, data)

def apply_lowpass_filter(data, sample_rate, cutoff=0.5, order=2):
    nyq = 0.5 * sample_rate
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low')
    return filtfilt(b, a, data)

def calculate_spo2(red_sig, ir_sig):
    # 1) 노치 + 밴드패스 → 노이즈 제거
    # red_bp = apply_bandpass_filter( apply_notch_filter(red_sig, PPG_SAMPLE_RATE, 60.0, 30.0),  PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    # ir_bp  = apply_bandpass_filter( apply_notch_filter(ir_sig,  PPG_SAMPLE_RATE, 60.0, 30.0),  PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    red_bp = apply_bandpass_filter( red_sig, PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    ir_bp  = apply_bandpass_filter( ir_sig, PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
        
    # 2) DC 추출: 저역 필터
    dc_ir  = apply_lowpass_filter(ir_sig,  PPG_SAMPLE_RATE, 0.5, 2)
    dc_red = apply_lowpass_filter(red_sig, PPG_SAMPLE_RATE, 0.5, 2)
    
    # 3) AC 성분: 원신호 - DC
    ac_ir  = ir_sig  - dc_ir
    ac_red = red_sig - dc_red
    
    # 4) R 비율 계산 (peak-to-peak 기준)
    ac_ir_pp  = np.max(ac_ir)  - np.min(ac_ir)
    ac_red_pp = np.max(ac_red) - np.min(ac_red)
    # DC는 저역 필터링된 값의 평균 또는 그 자체를 사용
    if np.mean(dc_ir)==0 or np.mean(dc_red)==0 or ac_ir_pp==0:
        return None
    R = (ac_red_pp/np.mean(dc_red)) / (ac_ir_pp/np.mean(dc_ir))
    
    # 5) SpO₂ 공식 적용
    spo2 = 110 - 25 * R
    return max(0.0, min(100.0, spo2))


# =====================================
# Callback Functions (For Notify)
# =====================================
def accelerometer_callback(sender, data):
    # print(f"({len(data)}) ")
    # print("Accelerometer data:", data)
    global acc_writer
    # timestamp = time.time()
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000 # ms 단위를 나누기 하여 sec 단위로

    for i in range(4, 184, 6):
        # accDataX = (data[i] << 8 | data[i+1])
        # accDataY = (data[i+2] << 8 | data[i+3])
        # accDataZ = (data[i+4] << 8 | data[i+5])
        # accDataX = (data[i] | data[i+1] << 8)
        # accDataY = (data[i+2] | data[i+3] << 8)
        # accDataZ = (data[i+4] | data[i+5] << 8)
        # accDataX >>= 4
        # accDataY >>= 4
        # accDataZ >>= 4

        accDataX = (data[i+1])
        accDataY = (data[i+3])
        accDataZ = (data[i+5])
        
        data_buffer["acc_x"].append(accDataX)
        data_buffer["acc_y"].append(accDataY)
        data_buffer["acc_z"].append(accDataZ)
        
        # CSV 파일에 기록
        if recording:
            acc_writer.writerow([timestamp, accDataX, accDataY, accDataZ])
            timestamp += 1.0 / ACC_SAMPLE_RATE  # 다음 샘플 타임스탬프 증가    
        
        # print(f"{data[i]},{data[i+1]}, - {data[i+2]},{data[i+3]}, - {data[i+4]},{data[i+5]} - {accDataX},{accDataY},{accDataZ}")
    
def battery_callback(sender, data):
    battery_level = int.from_bytes(data, byteorder='little')
    global_main_root.after(0, lambda lvl=battery_level: global_app.battery_info_label.config(text=f"Battery Level: {lvl}%"))

def eeg_notify_callback(sender, data):
    #print("eeg_notify_callback")
    global eeg_writer
    # timestamp = time.time()
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000 # ms 단위를 나누기 하여 sec 단위로
    # print(f"{timeRaw},{timestamp},{data[0]},{data[1]},{data[2]},{data[3]}")

    # 데이터 구조가 7바이트 단위로 반복되는 형식이고, 각 7바이트에서 ch1/ch2가 각각 3바이트씩 있음
    # 총 25개의 샘플이면 25 * 7 = 175바이트 + 앞 4바이트 헤더 = 179 바이트
    for i in range(4, 179, 7):
        # lead-off
        leadOff_raw = data[i]

        # 채널 1 (3바이트 → 24bit → 정수로 변환)
        ch1_raw = (data[i+1] << 16 | data[i+2] << 8 | data[i+3])
        ch2_raw = (data[i+4] << 16 | data[i+5] << 8 | data[i+6])        

        # 24bit signed 처리 (MSB 기준 음수 보정)
        if ch1_raw & 0x800000:
            ch1_raw -= 0x1000000
        if ch2_raw & 0x800000:
            ch2_raw -= 0x1000000

        # 전압값(uV)로 변환
        ch1_uv = ch1_raw * 4.033 / 12 / (2**23 - 1) * 1e6
        ch2_uv = ch2_raw * 4.033 / 12 / (2**23 - 1) * 1e6

        data_buffer["eeg1"].append(ch1_uv)
        data_buffer["eeg2"].append(ch2_uv)

        # CSV 파일에 기록
        if recording:
            eeg_writer.writerow([timestamp, leadOff_raw, ch1_uv, ch2_uv])
            timestamp += 1.0 / EEG_SAMPLE_RATE  # 다음 샘플 타임스탬프 증가            


def ppg_callback(sender, data):
    # print(f"({len(data)}) ")
    # print("PPG data:", data)
    global ppg_writer
    # timestamp = time.time()
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000 # ms 단위를 나누기 하여 sec 단위로

    for i in range(4, 168, 6):
        ppgRedData = (data[i] << 16 | data[i+1] << 8 | data[i+2])
        ppgIRData = (data[i+3] << 16 | data[i+4] << 8 | data[i+5])
        data_buffer["ppg"].append(ppgRedData)
        data_buffer["ppg_ir"].append(ppgIRData)

        # CSV 파일에 기록
        if recording:
            ppg_writer.writerow([timestamp, ppgRedData])
            timestamp += 1.0 / PPG_SAMPLE_RATE

# =====================================
# BLE Scanning and Connection Functions
# =====================================
async def scan_ble_devices():
    devices = await BleakScanner.discover()
    return devices

async def connect_ble(device_address):
    global disconnect_requested, global_ble_client, global_ble_loop
    client = BleakClient(device_address)
    try:
        await client.connect()
        global_ble_client = client
        global_ble_loop = asyncio.get_running_loop()
        #print("BLE device connected successfully")
        global_app.add_message("BLE device connected successfully")
        disconnect_requested = False
        while not disconnect_requested:
            await asyncio.sleep(1)
    except Exception as e:
        #print("BLE connection error:", e)
        global_app.add_message("BLE connection error:{e}")
    finally:
        await client.disconnect()
        global_ble_client = None
        #print("BLE device disconnected")
        global_app.add_message("BLE device disconnected")

def ble_thread_main(device_address):
    asyncio.run(connect_ble(device_address))

# =====================================
# Service Control Functions (Using notify)
# =====================================
def toggle_accelerometer(self):
    if global_ble_client is None or global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.accelerometer_running:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.start_notify(ACCELEROMETER_CHAR_UUID, accelerometer_callback),
                global_ble_loop)
            future.result()
            self.accelerometer_running = True
            self.accelerometer_button.config(text="Accelerometer Stop")            
            self.add_message("Accelerometer Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.stop_notify(ACCELEROMETER_CHAR_UUID),
                global_ble_loop)
            future.result()
            self.accelerometer_running = False
            self.accelerometer_button.config(text="Accelerometer Start")            
            self.add_message("Accelerometer Stopped")
    except Exception as e:        
        self.add_message("Accelrometer error: {e}")
        

def toggle_battery(self):
    if global_ble_client is None or global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.battery_running:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.start_notify(BATTERY_CHAR_UUID, battery_callback),
                global_ble_loop)
            future.result()
            self.battery_running = True
            self.battery_button.config(text="Battery Stop")
            self.add_message("Battery Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.stop_notify(BATTERY_CHAR_UUID),
                global_ble_loop)
            future.result()
            self.battery_running = False
            self.battery_button.config(text="Battery Start")
            self.add_message("Battery Stoppped")
    except Exception as e:
        self.add_message("Battery error: {e}")

def toggle_eeg_write(self):
    if global_ble_client is None or global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.eeg_write_running:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.write_gatt_char(EEG_WRITE_CHAR_UUID, b'start'),
                global_ble_loop)
            future.result()
            self.eeg_write_running = True
            self.eeg_write_button.config(text="EEG Write Stop")            
            self.add_message("EEG Write 'start' sent")
        else:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.write_gatt_char(EEG_WRITE_CHAR_UUID, b'stop'),
                global_ble_loop)
            future.result()
            self.eeg_write_running = False
            self.eeg_write_button.config(text="EEG Write Start")            
            self.add_message("EEG Write 'stop' sent")
    except Exception as e:        
        self.add_message("EEG Write error: {e}")

def toggle_eeg_notify(self):
    if global_ble_client is None or global_ble_loop is None:
        self.add_message("BLE not connected")
        return
    try:
        if not self.eeg_notify_running:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.start_notify(EEG_NOTIFY_CHAR_UUID, eeg_notify_callback),
                global_ble_loop)
            future.result()
            self.eeg_notify_running = True
            self.eeg_notify_button.config(text="EEG Notify Stop")            
            self.add_message("EEG Notify Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.stop_notify(EEG_NOTIFY_CHAR_UUID),
                global_ble_loop)
            future.result()
            self.eeg_notify_running = False
            self.eeg_notify_button.config(text="EEG Notify Start")
            self.add_message("EEG Notify Stopped")
    except Exception as e:
        self.add_message(f"EEG Notify error: {e}")

def toggle_ppg(self):
    if global_ble_client is None or global_ble_loop is None:
        self.add_message("BLE not connected")
        return
    try:
        if not self.ppg_running:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.start_notify(PPG_CHAR_UUID, ppg_callback),
                global_ble_loop)
            future.result()
            self.ppg_running = True
            self.ppg_button.config(text="PPG Stop")
            self.add_message("PPG Running")
            self.update_bpm()
        else:
            future = asyncio.run_coroutine_threadsafe(
                global_ble_client.stop_notify(PPG_CHAR_UUID),
                global_ble_loop)
            future.result()
            self.ppg_running = False
            self.ppg_button.config(text="PPG Start")
            self.add_message("PPG Stopped")
            data_buffer["ppg"].clear()
    except Exception as e:
        self.add_message(f"PPG error: {e}")


# =====================================
# Tkinter and matplotlib GUI Class (App)
# =====================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("BLE Device and Service Control")

        # 프로토콜 핸들러 등록: X 클릭 시 on_closing 호출
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Left Frame (Device selection and controls)
        left_frame = tk.Frame(root)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        tk.Label(left_frame, text="BLE Device Selection:", font=("Arial", 14, "bold")).pack(pady=5)        

        # listbox와 스크롤바를 위한 프레임 생성
        listbox_frame = tk.Frame(left_frame)
        listbox_frame.pack(pady=5, fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(listbox_frame, width=50)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
        # 세로 스크롤바 생성 및 listbox와 연동
        scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
                
        # Place Connect/Disconnect buttons on the same line
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(pady=5)
        self.connect_button = tk.Button(btn_frame, text="Connect", command=self.connect_device)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        self.disconnect_button = tk.Button(btn_frame, text="Disconnect", command=self.disconnect_device)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)        
        # self.rescan_button = tk.Button(left_frame, text="Rescan Devices", command=self.rescan_ble)
        # self.rescan_button.pack(pady=5)
        self.rescan_button = tk.Button(btn_frame, text="Rescan Devices", command=self.rescan_ble)
        self.rescan_button.pack(side=tk.LEFT, padx=5)
        
        
        # Battery information label
        self.battery_info_label = tk.Label(left_frame, text="Battery Info: N/A")
        self.battery_info_label.pack(pady=5)
        
        # Service Control Frame (Buttons for each service)
        service_frame = tk.Frame(left_frame, relief=tk.GROOVE, borderwidth=1)
        service_frame.pack(pady=10, fill=tk.X)
        tk.Label(service_frame, text="Service Control", font=("Arial", 14, "bold")).pack(pady=5)
        
        self.accelerometer_running = False
        self.battery_running = False
        self.eeg_write_running = False
        self.eeg_notify_running = False
        self.ppg_running = False
        
        self.accelerometer_button = tk.Button(service_frame, text="Accelerometer Start", command=lambda: toggle_accelerometer(self))
        self.accelerometer_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.battery_button = tk.Button(service_frame, text="Battery Start", command=lambda: toggle_battery(self))
        self.battery_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.eeg_write_button = tk.Button(service_frame, text="EEG Write Start", command=lambda: toggle_eeg_write(self))
        self.eeg_write_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.eeg_notify_button = tk.Button(service_frame, text="EEG Notify Start", command=lambda: toggle_eeg_notify(self))
        self.eeg_notify_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.ppg_button = tk.Button(service_frame, text="PPG Start", command=lambda: toggle_ppg(self))
        self.ppg_button.pack(fill=tk.X, padx=5, pady=2)

        self.notch_button = tk.Button(service_frame, text="Notch Filter: Off", command=self.toggle_notch)
        self.notch_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.bandpass_button = tk.Button(service_frame, text="Bandpass Filter: Off", command=self.toggle_bandpass)
        self.bandpass_button.pack(fill=tk.X, padx=5, pady=2)

         # FFT 버튼 - EEG1, EEG2 FFT를 한 창에서 구분하여 보여줌
        self.fft_button = tk.Button(left_frame, text="Show FFT", command=self.show_fft)
        self.fft_button.pack(pady=5)        
        
        # --- 2. Record 버튼 추가 ---
        record_frame = tk.Frame(left_frame)
        record_frame.pack(pady=5)
        self.record_btn = tk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_btn.pack(side=tk.LEFT)
        # ⏱️ 레코딩 타이머 라벨 추가
        self.record_timer_label = tk.Label(record_frame, text="00:00", font=("Arial", 12))
        self.record_timer_label.pack(side=tk.LEFT, padx=10)
        self.rcd_status_label = tk.Label(record_frame, text="Recording: OFF", font=("Arial", 12))
        self.rcd_status_label.pack(side=tk.LEFT, padx=5)

        # ⏱️ 레코딩 타이머 라벨 추가
        # self.record_timer_label = tk.Label(record_frame, text="00:00", font=("Arial", 10))
        # self.record_timer_label.pack(side=tk.LEFT, padx=10)

        self.record_start_time = None  # 시작 시각 저장용


        # --- 새로 추가: 메시지 로그용 리스트박스 (스크롤 가능) ---
        log_frame = tk.Frame(left_frame)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=5)
        
        tk.Label(log_frame, text="Message Log:").pack(anchor="w")
        
        # 메시지 로그 리스트박스와 스크롤바
        self.message_listbox = tk.Listbox(log_frame, width=60, height=10)
        self.message_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.log_scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_listbox.config(yscrollcommand=self.log_scrollbar.set)
        self.log_scrollbar.config(command=self.message_listbox.yview)
        # -----------------------------------------------------------
        
        # Right Frame (Real-time Plot Area)
        # Create 4 subplots: EEG Channel 1, EEG Channel 2, PPG Data, Accelerometer Data
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.fig, self.axs = plt.subplots(4, 1, figsize=(10, 10))  # 너비 키움
        self.fig.tight_layout(pad=3.0)

        
        # EEG Channel 1 (subplot 0)
        self.line_eeg1, = self.axs[0].plot([], [], label="EEG Channel 1")
        self.axs[0].legend()
        
        # EEG Channel 2 (subplot 1)
        self.line_eeg2, = self.axs[1].plot([], [], label="EEG Channel 2")
        self.axs[1].legend()
        
        # PPG Data (subplot 2)
        self.line_ppg, = self.axs[2].plot([], [], label="PPG Data")
        self.axs[2].legend()
        
        # Accelerometer Data (subplot 3)
        self.line_acc_x, = self.axs[3].plot([], [], label="Acc X")
        self.line_acc_y, = self.axs[3].plot([], [], label="Acc Y")
        self.line_acc_z, = self.axs[3].plot([], [], label="Acc Z")
        self.axs[3].legend()
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self.update_plot()
    
    # =====================================
    # Recording toggle method
    # =====================================
    def toggle_recording(self):
        global recording, eeg_file, ppg_file, acc_file, eeg_writer, ppg_writer, acc_writer

        if not recording:
            # 시작 시각
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            RAW_DIR.mkdir(exist_ok=True)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            eeg_file = open(RAW_DIR / f'eeg_{timestamp_str}.csv', 'w', newline='')
            ppg_file = open(RAW_DIR / f'ppg_{timestamp_str}.csv', 'w', newline='')
            acc_file = open(RAW_DIR / f'acc_{timestamp_str}.csv', 'w', newline='')

            eeg_writer = csv.writer(eeg_file)
            ppg_writer = csv.writer(ppg_file)
            acc_writer = csv.writer(acc_file)
            eeg_writer.writerow(['timestamp', 'lead-off', 'ch1(µV)', 'ch2(µV)'])
            ppg_writer.writerow(['timestamp', 'ppg_raw'])
            acc_writer.writerow(['timestamp', 'acc_x', 'acc_y', 'acc_z'])

            recording = True
            self.record_btn.config(text="Stop Recording")
            self.rcd_status_label.config(text="Recording: ON 🟢", font=("Arial", 12))
            self.record_start_time = time.time()  # ⏱️ 시작 시각 저장
            self.update_record_timer()            # ⏱️ 타이머 시작
            self.add_message(f"Recording started at {now_str}")
            self.add_message(f"Recording started → saved in raw_data/ (prefix: {timestamp_str})")
        else:
            # 레코딩 종료 시각
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            recording = False            
            self.record_btn.config(text="Start Recording")
            self.rcd_status_label.config(text="Recording: OFF ⚪")
            self.record_timer_label.config(text="00:00")  # ⏹️ 타이머 초기화
            
            for f in (eeg_file, ppg_file, acc_file):
                if f:
                    f.close()
            eeg_file = ppg_file = acc_file = None
            eeg_writer = ppg_writer = acc_writer = None
            
            # 🕒 녹음 시간 계산
            if self.record_start_time is not None:
                duration = int(time.time() - self.record_start_time)
                minutes = duration // 60
                seconds = duration % 60
                self.add_message(f"⏱️ Total recording duration: {minutes}분 {seconds}초")
            self.record_start_time = None

            self.add_message(f"Recording stopped at {now_str}")            

    def update_record_timer(self):
        if recording and self.record_start_time is not None:
            elapsed = int(time.time() - self.record_start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.record_timer_label.config(text=f"{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_record_timer)



    def on_closing(self):
        # (옵션) 깨끗이 리소스 정리, 스레드 종료 등 수행
        if global_ble_client: asyncio.run(global_ble_client.disconnect())

        # 메인 윈도우 닫고
        self.root.destroy()
        # 완전 종료
        sys.exit(0)
    
    def update_plot(self):
        # EEG Channel 1 (subplot 0)
        t = np.arange(len(data_buffer["eeg1"])) / EEG_SAMPLE_RATE
        if len(t) > EEG_MAX_PLOT_POINTS:
            t = t[-EEG_MAX_PLOT_POINTS:]
            eeg1 = np.array(data_buffer["eeg1"])[-EEG_MAX_PLOT_POINTS:]
        else:
            eeg1 = np.array(data_buffer["eeg1"])
        if len(t) > 0:
            if filter_notch_enabled:
                eeg1 = apply_notch_filter(eeg1, EEG_SAMPLE_RATE, 60.0,40.0)
            if filter_bandpass_enabled:
                eeg1 = apply_bandpass_filter(eeg1, EEG_SAMPLE_RATE, 1.0, 50.0)
            self.line_eeg1.set_data(t, eeg1)
            self.axs[0].relim()
            self.axs[0].autoscale_view()
            self.axs[0].set_title("EEG Channel 1 " + ("(Filtered)" if (filter_notch_enabled or filter_bandpass_enabled) else ""))
        
        # EEG Channel 2 (subplot 1)
        t2 = np.arange(len(data_buffer["eeg2"])) / EEG_SAMPLE_RATE
        if len(t2) > EEG_MAX_PLOT_POINTS:
            t2 = t2[-EEG_MAX_PLOT_POINTS:]
            eeg2 = np.array(data_buffer["eeg2"])[-EEG_MAX_PLOT_POINTS:]
        else:
            eeg2 = np.array(data_buffer["eeg2"])
        if len(t2) > 0:
            if filter_notch_enabled:
                eeg2 = apply_notch_filter(eeg2, EEG_SAMPLE_RATE, 60.0,40.0)
            if filter_bandpass_enabled:
                eeg2 = apply_bandpass_filter(eeg2, EEG_SAMPLE_RATE, 1.0, 50.0)
            self.line_eeg2.set_data(t2, eeg2)
            self.axs[1].relim()
            self.axs[1].autoscale_view()
            self.axs[1].set_title("EEG Channel 2 " + ("(Filtered)" if (filter_notch_enabled or filter_bandpass_enabled) else ""))
        
        # PPG Data (subplot 2)
        t_ppg = np.arange(len(data_buffer["ppg"])) / 50
        if len(t_ppg) > PPG_MAX_PLOT_POINTS:
            t_ppg = t_ppg[-PPG_MAX_PLOT_POINTS:]
            ppg = np.array(data_buffer["ppg"])[-PPG_MAX_PLOT_POINTS:]
        else:
            ppg = np.array(data_buffer["ppg"])
        if len(t_ppg) > 0:
            self.line_ppg.set_data(t_ppg, ppg)
            self.axs[2].relim()
            self.axs[2].autoscale_view()
            self.axs[2].set_title("PPG Data")
        
        # Accelerometer Data (subplot 3)
        t_acc = np.arange(len(data_buffer["acc_x"])) / ACC_SAMPLE_RATE
        if len(t_acc) > ACC_MAX_PLOT_POINTS:
            t_acc = t_acc[-ACC_MAX_PLOT_POINTS:]
            acc_x = np.array(data_buffer["acc_x"])[-ACC_MAX_PLOT_POINTS:]
            acc_y = np.array(data_buffer["acc_y"])[-ACC_MAX_PLOT_POINTS:]
            acc_z = np.array(data_buffer["acc_z"])[-ACC_MAX_PLOT_POINTS:]
        else:
            acc_x = np.array(data_buffer["acc_x"])
            acc_y = np.array(data_buffer["acc_y"])
            acc_z = np.array(data_buffer["acc_z"])
        if len(t_acc) > 0:
            self.line_acc_x.set_data(t_acc, acc_x)
            self.line_acc_y.set_data(t_acc, acc_y)
            self.line_acc_z.set_data(t_acc, acc_z)
            self.axs[3].relim()
            self.axs[3].autoscale_view()
            self.axs[3].set_title("Accelerometer Data")
        
        self.canvas.draw_idle()
        self.root.after(200, self.update_plot)
    
    def update_device_list(self, devices):
        self.listbox.delete(0, tk.END)
        for dev in devices:
            self.listbox.insert(tk.END, f"{dev.name}: {dev.address}")
        self.add_message(f"{len(devices)} devices found")
    
    def connect_device(self):
        try:
            selected = self.listbox.get(self.listbox.curselection())
        except tk.TclError:
            self.add_message("Select a device")
            return
        device_address = selected.split(":")[-1].strip()
        threading.Thread(target=ble_thread_main, args=(device_address,), daemon=True).start()
        self.add_message(f"{selected} Connecting...")
    
    def disconnect_device(self):
        global disconnect_requested
        disconnect_requested = True
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
    
    def rescan_ble(self):
        self.listbox.delete(0, tk.END)
        threading.Thread(target=scan_devices_background, args=(self,), daemon=True).start()

    # 필터 토글 함수 (Notch, Bandpass)
    def toggle_notch(self):
        global filter_notch_enabled
        filter_notch_enabled = not filter_notch_enabled
        self.notch_button.config(text="Notch Filter: " + ("On" if filter_notch_enabled else "Off"))
    
    def toggle_bandpass(self):
        global filter_bandpass_enabled
        filter_bandpass_enabled = not filter_bandpass_enabled
        self.bandpass_button.config(text="Bandpass Filter: " + ("On" if filter_bandpass_enabled else "Off"))

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
        # EEG1 데이터 FFT
        #data_eeg1 = np.array(data_buffer["eeg1"])
        #data_eeg2 = np.array(data_buffer["eeg2"])
        data_eeg1 = np.array(data_buffer["eeg1"][-1000:])
        data_eeg2 = np.array(data_buffer["eeg2"][-1000:])
        
        
        # 필터 적용 (노치, 밴드패스 선택에 따라)
        if filter_notch_enabled:
            if data_eeg1.size > 0:
                data_eeg1 = apply_notch_filter(data_eeg1, SAMPLE_RATE, 60.0, 30.0)
            if data_eeg2.size > 0:
                data_eeg2 = apply_notch_filter(data_eeg2, SAMPLE_RATE, 60.0, 30.0)
        if filter_bandpass_enabled:
            if data_eeg1.size > 0:
                data_eeg1 = apply_bandpass_filter(data_eeg1, SAMPLE_RATE, 1.0, 50.0)
            if data_eeg2.size > 0:
                data_eeg2 = apply_bandpass_filter(data_eeg2, SAMPLE_RATE, 1.0, 50.0)
        
        # EEG1 FFT 계산 및 업데이트
        if data_eeg1.size > 0:
            n1 = len(data_eeg1)
            fft_values1 = np.fft.rfft(data_eeg1)
            fft_freqs1 = np.fft.rfftfreq(n1, d=1.0/SAMPLE_RATE)
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
            fft_freqs2 = np.fft.rfftfreq(n2, d=1.0/SAMPLE_RATE)
            magnitude2 = np.abs(fft_values2)
            self.fft_line2.set_data(fft_freqs2, magnitude2)
            self.ax2.relim()
            self.ax2.autoscale_view()
        else:
            self.fft_line2.set_data([], [])
        
        self.fft_canvas.draw_idle()
        # FFT 창이 열려 있다면 500ms 후에 다시 업데이트
        if hasattr(self, 'fft_window') and self.fft_window.winfo_exists():
            self.fft_window.after(500, self.update_fft)    

    def update_bpm(self):
        # print("update_bpm called")
        if disconnect_requested or not self.ppg_running:
            data_buffer["ppg"].clear()
            return
        
        try:
            recent_ppg = np.array(data_buffer["ppg"][-500:])  # 10초치 (50Hz)
            recent_ppg_ir  = np.array(data_buffer["ppg_ir"][-500:])
            print("recent_ppg length:", len(recent_ppg))
            if len(recent_ppg) >= 250 and len(recent_ppg_ir) >= 250:  # 최소한 5초 이상 확보
                # wd, m = hp.process(recent_ppg, sample_rate=PPG_SAMPLE_RATE)
                # print("wd:", wd)
                # 1️⃣ 필터 적용 (0.7 ~ 3.5Hz → 약 42 ~ 210 bpm)
                filtered_ppg = hp.filter_signal(recent_ppg, cutoff=[0.7, 3.5], sample_rate=PPG_SAMPLE_RATE, order=3, filtertype='bandpass')
                wd, m = hp.process(filtered_ppg, sample_rate=PPG_SAMPLE_RATE)
                # wd, m = hp.process(filtered_ppg, sample_rate=50, peakwindow=0.5, ma_perc=15)
                bpm_val = m['bpm']
                sdnn_val = m['sdnn']
                ibi_val = m['ibi']
                # self.bpm_label.config(text=f"BPM: {bpm_val:.1f}")
                spo2 = calculate_spo2(recent_ppg, recent_ppg_ir)
                print(f"BPM: {bpm_val:.1f}, SDNN: {sdnn_val:.1f} ms, IBI: {ibi_val:.1f} ms, SPO2: {spo2:.1f}%")
                # print(wd['RR_list'])
                
            else:
                # self.bpm_label.config(text="BPM: --")
                print("BPM:--")
        except Exception as e:
            # 노이즈 등으로 분석 실패할 경우
            # self.bpm_label.config(text="BPM: --")
            print("Error in update_bpm:", e)
            print("BPM:xx")
        finally:
            if not disconnect_requested:                
                self.root.after(1000, self.update_bpm)  # 1초마다 반복
    
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


# =====================================
# BLE Device Scan in Background
# =====================================
def scan_devices_background(app):
    global_app.add_message("Scan BLE devices...")
    devices = asyncio.run(scan_ble_devices())
    app.root.after(0, lambda: app.update_device_list(devices))

# =====================================
# Main Function
# =====================================
def main():
    global global_main_root, global_app
    root = tk.Tk()
    global_main_root = root
    app = App(root)
    global_app = app
    threading.Thread(target=scan_devices_background, args=(app,), daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    main()
