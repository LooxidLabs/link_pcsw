"""User UI preferences persisted as JSON next to the app / exe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import constants, state

SETTINGS_FILENAME = "user_settings.json"

DEFAULTS: dict[str, Any] = {
    "lxb_filter_only": True,
    "eeg_raw_print": False,
    "auto_test_mode": False,
    "bpm_calc_enabled": False,
    "eeg_pga_gain": constants.EEG_PGA_GAIN_DEFAULT,
}


def settings_path() -> Path:
    return state.APP_BASE_DIR / SETTINGS_FILENAME


def _normalize(data: Any) -> dict[str, Any]:
    """Merge loaded data with defaults and validate types."""
    out = DEFAULTS.copy()
    if not isinstance(data, dict):
        return out

    for key in ("lxb_filter_only", "eeg_raw_print", "auto_test_mode", "bpm_calc_enabled"):
        value = data.get(key)
        if isinstance(value, bool):
            out[key] = value

    gain = data.get("eeg_pga_gain")
    if gain in constants.EEG_PGA_GAIN_OPTIONS:
        out["eeg_pga_gain"] = int(gain)

    return out


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return DEFAULTS.copy()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _normalize(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return DEFAULTS.copy()


def save_settings(data: dict[str, Any]) -> bool:
    path = settings_path()
    normalized = _normalize(data)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(normalized, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def collect_from_app(app) -> dict[str, Any]:
    return {
        "lxb_filter_only": bool(app.lxb_filter_var.get()),
        "eeg_raw_print": bool(app.eeg_raw_print_var.get()),
        "auto_test_mode": bool(app.auto_test_var.get()),
        "bpm_calc_enabled": bool(app.bpm_calc_enabled_var.get()),
        "eeg_pga_gain": int(state.eeg_pga_gain),
    }
