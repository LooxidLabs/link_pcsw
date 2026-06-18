"""EEG lead-off 바이트 디코딩 (펌웨어 v1.42+ / docs/eeg-raw-data-format.md)."""

from __future__ import annotations

# bit0=IN1P, bit1=IN1N, bit2=IN2P, bit3=IN2N — 1=lead-off(이탈), 0=lead-on(접촉)
LEAD_OFF_ELECTRODES: tuple[tuple[str, int, str], ...] = (
    ("IN1P", 0, "CH1 +"),
    ("IN1N", 1, "CH1 -"),
    ("IN2P", 2, "CH2 +"),
    ("IN2N", 3, "CH2 -"),
)


def decode_electrodes(lead_off: int) -> dict[str, bool]:
    """전극별 lead-off 여부 반환. True=이탈(off), False=접촉(on)."""
    return {
        name: bool(lead_off & (1 << bit))
        for name, bit, _label in LEAD_OFF_ELECTRODES
    }


def electrode_contact_ok(lead_off: int, electrode: str) -> bool:
    """해당 전극 접촉 여부. 접촉= True."""
    for name, bit, _label in LEAD_OFF_ELECTRODES:
        if name == electrode:
            return (lead_off & (1 << bit)) == 0
    raise KeyError(f"unknown electrode: {electrode}")


def channel_contact_ok(lead_off: int, channel: int) -> bool:
    """CH1/CH2 P·N 모두 접촉이면 True."""
    if channel == 1:
        return (lead_off & 0x03) == 0
    if channel == 2:
        return (lead_off & 0x0C) == 0
    raise ValueError("channel must be 1 or 2")
