"""Signal processing helpers."""
import numpy as np
from scipy.signal import iirnotch, butter, filtfilt

from app import constants

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
    # red_bp = apply_bandpass_filter( apply_notch_filter(red_sig, constants.PPG_SAMPLE_RATE, 60.0, 30.0),  constants.PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    # ir_bp  = apply_bandpass_filter( apply_notch_filter(ir_sig,  constants.PPG_SAMPLE_RATE, 60.0, 30.0),  constants.PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    red_bp = apply_bandpass_filter( red_sig, constants.PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
    ir_bp  = apply_bandpass_filter( ir_sig, constants.PPG_SAMPLE_RATE, 0.5, 5.0, 3 )
        
    # 2) DC 추출: 저역 필터
    dc_ir  = apply_lowpass_filter(ir_sig,  constants.PPG_SAMPLE_RATE, 0.5, 2)
    dc_red = apply_lowpass_filter(red_sig, constants.PPG_SAMPLE_RATE, 0.5, 2)
    
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
