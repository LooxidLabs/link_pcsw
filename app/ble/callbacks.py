"""BLE notify callbacks."""
import time

from app import state
from app import constants
from app.signal import acc_scale
from app.signal import eeg_scale

def accelerometer_callback(sender, data):
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000  # device clock (sec)

    header = constants.ACC_PACKET_HEADER_BYTES
    stride = constants.ACC_BYTES_PER_SAMPLE
    end = header + constants.ACC_SAMPLES_PER_PACKET * stride

    for sample_idx, i in enumerate(range(header, end, stride)):
        acc_x, acc_y, acc_z = acc_scale.parse_sample_xyz(data, i)

        state.data_buffer["acc_x"].append(acc_x)
        state.data_buffer["acc_y"].append(acc_y)
        state.data_buffer["acc_z"].append(acc_z)

        if state.recording:
            sample_ts = timestamp + sample_idx / constants.ACC_SAMPLE_RATE
            state.acc_writer.writerow([sample_ts, acc_x, acc_y, acc_z])

        if state.global_app is not None and not state.shutting_down:
            state.global_app.acc_times.append(time.time())
    
def battery_callback(sender, data):
    battery_level = int.from_bytes(data, byteorder='little')
    state._run_on_ui(
        lambda lvl=battery_level: state.global_app.battery_info_label.config(
            text=f"Battery Level: {lvl}%"
        )
    )


def _schedule_battery_label(level: int):
    """메인 스레드에서 배터리 라벨 갱신"""
    if state.global_app is None:
        return
    state._run_on_ui(
        lambda lvl=level: state.global_app.battery_info_label.config(text=f"Battery Level: {lvl}%")
    )

def _eeg_raw_print_enabled() -> bool:
    return state.eeg_raw_print_enabled


def eeg_notify_callback(sender, data):
    #print("eeg_notify_callback")
    # timestamp = time.time()
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000 # ms 단위를 나누기 하여 sec 단위로
    # print(f"{timeRaw},{timestamp},{data[0]},{data[1]},{data[2]},{data[3]}")

    print_raw = _eeg_raw_print_enabled()
    if print_raw:
        print(f"[EEG RAW packet] len={len(data)} hex={bytes(data).hex()}", flush=True)

    # 데이터 구조가 7바이트 단위로 반복되는 형식이고, 각 7바이트에서 ch1/ch2가 각각 3바이트씩 있음, 맨 앞 1바이트는 lead-off
    # 총 25개의 샘플이면 25 * 7 = 175바이트 + 앞 4바이트 헤더 = 179 바이트
    sample_idx = 0
    latest_lead_off: int | None = None
    for i in range(4, 179, 7):
        # lead-off
        leadOff_raw = data[i]
        latest_lead_off = leadOff_raw

        # 채널 1 (3바이트 → 24bit → 정수로 변환)
        ch1_raw = (data[i+1] << 16 | data[i+2] << 8 | data[i+3])
        ch2_raw = (data[i+4] << 16 | data[i+5] << 8 | data[i+6])        

        # 24bit signed 처리 (MSB 기준 음수 보정)
        if ch1_raw & 0x800000:
            ch1_raw -= 0x1000000
        if ch2_raw & 0x800000:
            ch2_raw -= 0x1000000

        # 전압값(uV)로 변환
        gain = state.eeg_pga_gain
        ch1_uv = eeg_scale.raw_to_uv(ch1_raw, gain)
        ch2_uv = eeg_scale.raw_to_uv(ch2_raw, gain)

        state.data_buffer["eeg1"].append(ch1_uv)
        state.data_buffer["eeg2"].append(ch2_uv)

        if print_raw:
            sample_ts = timestamp + sample_idx / constants.EEG_SAMPLE_RATE
            print(
                f"[EEG RAW] ts={sample_ts:.6f} leadOff={leadOff_raw} "
                f"ch1={ch1_raw} ch2={ch2_raw} ch1_uv={ch1_uv:.3f} ch2_uv={ch2_uv:.3f}",
                flush=True,
            )

        # CSV 파일에 기록
        if state.recording:
            state.eeg_writer.writerow([timestamp, leadOff_raw, ch1_uv, ch2_uv])
            timestamp += 1.0 / constants.EEG_SAMPLE_RATE  # 다음 샘플 타임스탬프 증가

        sample_idx += 1
        if state.global_app is not None and not state.shutting_down:
            state.global_app.eeg_times.append(time.time())

    if latest_lead_off is not None:
        state.update_eeg_lead_off(latest_lead_off)


def ppg_callback(sender, data):
    # print(f"({len(data)}) ")
    # print("PPG data:", data)
    # timestamp = time.time()
    timeRaw = (data[3] << 24 | data[2] << 16 | data[1] << 8 | data[0])
    timestamp = timeRaw / 32.768 / 1000 # ms 단위를 나누기 하여 sec 단위로

    # 데이터 구조가 6바이트 단위로 반복되는 형식, 앞에 3바이트는 PPG RED, 다음 3바이트는 PPG IR
    # 총 28개의 샘플이면 28 * 6 = 168바이트 + 앞 4바이트 헤더 = 172 바이트
    for i in range(4, 172, 6):
        ppgRedData = (data[i] << 16 | data[i+1] << 8 | data[i+2])
        ppgIRData = (data[i+3] << 16 | data[i+4] << 8 | data[i+5])
        state.data_buffer["ppg"].append(ppgRedData)
        state.data_buffer["ppg_ir"].append(ppgIRData)

        # CSV 파일에 기록
        if state.recording:
            state.ppg_writer.writerow([timestamp, ppgRedData, ppgIRData])
            timestamp += 1.0 / constants.PPG_SAMPLE_RATE
    
        if state.global_app is not None and not state.shutting_down:
            state.global_app.ppg_times.append(time.time())
