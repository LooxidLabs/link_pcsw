# EEG BLE 로우 데이터 구조

PC 소프트웨어(link_pcsw 등)에서 BLE로 수신한 EEG notify 데이터를 파싱하고, lead-off 신호를 표현할 때 참고하는 문서입니다.

펌웨어 기준: `lxhb_fw` v1.42+

---

## 1. BLE Notify 패킷 전체 구조

**1패킷 = 179바이트** (`EEG_BT_CNT`)

```
[0..3]   timestamp (4B, little-endian uint32)
[4..178] EEG 샘플 25개 × 7바이트
```

| 항목 | 값 |
|------|-----|
| 패킷 크기 | **179 bytes** |
| 샘플 수/패킷 | **25** |
| 샘플레이트 | **250 Hz** (기본) |
| 패킷 주기 | **100 ms** (25 ÷ 250) |
| GATT Service UUID | `df7b5d95-3afe-00a1-084c-b50895ef4f95` |
| GATT TX (Notify) UUID | `00ab4d15-66b4-0d8a-824f-8d6f8966c6e5` |

펌웨어 정의 (`main.c`):

```c
#define EEG_DATA_CNT        7       // 샘플 1개 크기
#define EEG_PCK_NUM         25      // 패킷당 샘플 수 (iOS MTU 기준)
#define EEG_TOTAL_DATA_SIZE (EEG_PCK_NUM * EEG_DATA_CNT)  // 175
#define EEG_BT_CNT          (4 + EEG_TOTAL_DATA_SIZE)     // 179
```

---

## 2. 샘플 1개 구조 (7바이트)

```
offset  크기  내용
------  ----  ----
+0      1B    lead-off (압축 4bit, 아래 참고)
+1..3   3B    CH1 raw ADC (24-bit signed, MSB first)
+4..6   3B    CH2 raw ADC (24-bit signed, MSB first)
```

**중요:** ADS1292 status 3바이트는 BLE로 보내지 않습니다. lead-off만 **1바이트로 압축**해 전송합니다.

채널 매핑 (회로도 / ADS1292):

| 회로 | ADS1292 | BLE 바이트 |
|------|---------|------------|
| 1P/1N | CH1 (IN1P/IN1N) | `+1..+3` |
| 2P/2N | CH2 (IN2P/IN2N) | `+4..+6` |

---

## 3. 타임스탬프 (바이트 0~3)

펌웨어: `k_cycle_get_32()` 기반 tick (32768 Hz), little-endian 4바이트로 패킷 앞에 기록.

```python
time_raw = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
timestamp_sec = time_raw / 32768.0  # 초 단위
```

패킷 내 25샘플은 **첫 샘플 = 패킷 timestamp**, 이후 샘플은 `+ 1/250` 초씩 증가.

```python
EEG_SAMPLE_RATE = 250.0

for sample_idx in range(25):
    sample_ts = timestamp_sec + sample_idx / EEG_SAMPLE_RATE
```

---

## 4. CH1 / CH2 raw → µV 변환

24-bit **signed**, MSB first (big-endian 3바이트):

```python
def parse_int24_msb(b0, b1, b2):
    val = (b0 << 16) | (b1 << 8) | b2
    if val & 0x800000:
        val -= 0x1000000
    return val

ch1_raw = parse_int24_msb(data[i+1], data[i+2], data[i+3])
ch2_raw = parse_int24_msb(data[i+4], data[i+5], data[i+6])
```

µV 변환 (link_pcsw `callbacks.py`와 동일):

```python
GAIN = 12
VREF = 4.033  # 앱 기준 (펌웨어 VREF 4.0V와 ~0.8% 차이)

def raw_to_uv(raw):
    return raw * VREF / GAIN / (2**23 - 1) * 1e6
```

| raw | 의미 |
|-----|------|
| `8388607` (0x7FFFFF) | 양의 full-scale 포화 |
| `-8388608` (0x800000) | 음의 full-scale 포화 |
| 포화 시 µV | 약 **±336,083 µV** |

펌웨어 Gain 설정: `ads1292.c` → `GAIN_12` (CH1/CH2 모두)

---

## 5. lead-off 바이트

### 5.1 펌웨어 압축 방식

ADS1292 SPI 9바이트 중 status 3바이트(`eeg_buf[0..2]`)에서 **4bit만** 추출:

```c
lead_off = ((eeg_buf[0] & 0x07) << 1) | ((eeg_buf[1] & 0x80) >> 7);
```

역매핑 (ADS1292 LOFF_STAT[3:0]):

```
lead_off bit3 = IN2N_OFF  (CH2 N 전극)
lead_off bit2 = IN2P_OFF  (CH2 P 전극)
lead_off bit1 = IN1N_OFF  (CH1 N 전극)
lead_off bit0 = IN1P_OFF  (CH1 P 전극)
```

**1 = lead-off(이탈), 0 = lead-on(접촉)**

> RLD_STAT (LOFF_STAT bit4)는 BLE lead-off 바이트에 **포함되지 않음**.

### 5.2 값 해석표

| lead_off | bit3~0 | 의미 |
|----------|--------|------|
| `0x00` | 0000 | 4전극 모두 접촉 |
| `0x0F` | 1111 | 4전극 모두 이탈 |
| `0x07` | 0111 | IN2N, IN2P, IN1N 이탈 |
| `0x0A` | 1010 | IN2P, IN1N 이탈 |
| `0x0D` | 1101 | IN2N, IN2P, IN1P 이탈 |

펌웨어 LED 기준 (`leadOffLedControl`):

| lead_off | WHITE LED |
|----------|-----------|
| `0x0F` | ON (전극 이탈) |
| `0x00`, `0x07`, `0x0A`, `0x0D` | OFF (측정 가능 상태) |

### 5.3 PC 표현용 헬퍼 코드

```python
LEAD_OFF_NAMES = {
    0: "IN1P",  # bit0
    1: "IN1N",  # bit1
    2: "IN2P",  # bit2
    3: "IN2N",  # bit3
}

def decode_lead_off(lead_off: int) -> dict:
    """lead-off 1바이트 → 전극별 상태"""
    electrodes = {
        name: bool(lead_off & (1 << bit))
        for bit, name in LEAD_OFF_NAMES.items()
    }
    return {
        "raw": lead_off,
        "all_off": lead_off == 0x0F,
        "all_on": lead_off == 0x00,
        "any_off": lead_off != 0x00,
        "electrodes": electrodes,
        "off_list": [n for n, off in electrodes.items() if off],
        "on_list":  [n for n, off in electrodes.items() if not off],
    }

def lead_off_status_text(lead_off: int) -> str:
    d = decode_lead_off(lead_off)
    if d["all_off"]:
        return "ALL OFF"
    if d["all_on"]:
        return "OK"
    return "OFF: " + ", ".join(d["off_list"])

def lead_off_color(lead_off: int) -> str:
    if lead_off == 0x00:
        return "green"    # 정상
    if lead_off == 0x0F:
        return "red"        # 전극 전부 이탈
    return "orange"         # 부분 이탈

def channel_lead_off_ok(lead_off: int, channel: int) -> bool:
    """channel 1 or 2 — P/N 둘 다 접촉이면 True"""
    if channel == 1:
        return (lead_off & 0x03) == 0   # IN1P, IN1N
    if channel == 2:
        return (lead_off & 0x0C) == 0   # IN2P, IN2N
    raise ValueError("channel must be 1 or 2")
```

---

## 6. 전체 파서 예시 (Python)

```python
EEG_PACKET_SIZE = 179
EEG_SAMPLE_COUNT = 25
EEG_BYTES_PER_SAMPLE = 7
EEG_SAMPLE_RATE = 250.0

def parse_eeg_packet(data: bytes):
    if len(data) < EEG_PACKET_SIZE:
        raise ValueError(f"expected {EEG_PACKET_SIZE} bytes, got {len(data)}")

    ts0 = int.from_bytes(data[0:4], byteorder="little") / 32768.0
    samples = []

    for n in range(EEG_SAMPLE_COUNT):
        i = 4 + n * EEG_BYTES_PER_SAMPLE
        lead_off = data[i]
        ch1_raw = parse_int24_msb(data[i+1], data[i+2], data[i+3])
        ch2_raw = parse_int24_msb(data[i+4], data[i+5], data[i+6])

        samples.append({
            "timestamp": ts0 + n / EEG_SAMPLE_RATE,
            "lead_off": lead_off,
            "lead_off_info": decode_lead_off(lead_off),
            "ch1_raw": ch1_raw,
            "ch2_raw": ch2_raw,
            "ch1_uv": raw_to_uv(ch1_raw),
            "ch2_uv": raw_to_uv(ch2_raw),
            "ch1_ok": channel_lead_off_ok(lead_off, 1),
            "ch2_ok": channel_lead_off_ok(lead_off, 2),
        })

    return samples
```

---

## 7. CSV 레코딩 형식 (link_pcsw)

`link_pcsw` 레코딩 CSV 헤더:

```csv
timestamp,lead-off,ch1(µV),ch2(µV)
```

- `timestamp`: 초 단위 float, 샘플마다 `+ 1/250` 증가
- `lead-off`: 0~15 정수 (압축 lead-off raw 값)
- `ch1(µV)`, `ch2(µV)`: 위 µV 변환식 적용 결과

---

## 8. 주의사항

1. **lead-off ≠ 신호 품질**  
   `lead_off=0`이어도 ADC 포화(±336,083 µV) 가능. 포화는 raw `±0x7FFFFF`로 별도 판단.

2. **RLD 상태 미포함**  
   압축 lead-off는 LOFF_STAT[3:0]만 포함. RLD 전극 상태는 BLE에 없음.

3. **v1.42+ hold**  
   SPI status invalid 시 **직전 샘플의 lead-off/CH가 반복**될 수 있음. 글리치 구간에서 lead-off가 1샘플만 튀는 현상은 줄어듦.

4. **기존 link_pcsw 파서**  
   `link_pcsw/app/ble/callbacks.py`의 `eeg_notify_callback()`이 위 구조와 일치.

---

## 9. 바이트 레이아웃 다이어그램

```
Packet [179 bytes]
┌─────────────────────────────────────────────────────────────┐
│ ts[0] ts[1] ts[2] ts[3] │ sample0 │ sample1 │ ... │ sample24 │
│  ← uint32 LE tick/32768 →│  7B     │  7B     │     │   7B     │
└─────────────────────────────────────────────────────────────┘

Sample [7 bytes]
┌──────┬─────────────┬─────────────┐
│ lead │  CH1 (3B)   │  CH2 (3B)   │
│ off  │ MSB..LSB    │ MSB..LSB    │
│ 1B   │ signed int24│ signed int24│
└──────┴─────────────┴─────────────┘

lead-off bit map
 bit3    bit2    bit1    bit0
 IN2N    IN2P    IN1N    IN1P
 1=off   1=off   1=off   1=off
```

---

## 10. 관련 펌웨어 파일

| 파일 | 내용 |
|------|------|
| `lxhb_fw/src/main.c` | EEG 패킹, lead-off 추출, BLE 전송 |
| `lxhb_fw/src/hw/ads1292.c` | ADS1292 SPI read, status 검증 (v1.42+) |
| `lxhb_fw/src/services/custom_service.c` | EEG GATT service, notify |
| `lxhb_fw/src/services/custom_service.h` | EEG UUID 정의 |
| `link_pcsw/app/ble/callbacks.py` | PC측 EEG notify 파서 |
