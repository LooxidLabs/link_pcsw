"""EEG raw ADC → µV conversion."""

from __future__ import annotations

from app import constants

EEG_VREF = constants.EEG_VREF


def raw_to_uv(raw: int, gain: int) -> float:
    """24bit signed raw → µV. gain: PGA gain (8 or 12)."""
    if gain not in constants.EEG_PGA_GAIN_OPTIONS:
        gain = constants.EEG_PGA_GAIN_DEFAULT
    return raw * EEG_VREF / gain / (2**23 - 1) * 1e6
