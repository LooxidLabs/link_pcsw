"""EEG lead-off 4-LED 인디케이터 패널."""

from __future__ import annotations

import tkinter as tk

from app import constants
from app.signal.lead_off import LEAD_OFF_ELECTRODES

COLOR_CONTACT = "#43a047"  # green — lead-on
COLOR_LEAD_OFF = "#e53935"  # red — lead-off
COLOR_UNKNOWN = "#9e9e9e"  # gray — 데이터 없음


class LeadOffPanel:
    """CH1/CH2 P·N 전극 4개 LED 표시."""

    def __init__(self, parent: tk.Misc, width: int | None = None) -> None:
        panel_width = width if width is not None else constants.LEAD_OFF_PANEL_WIDTH_PX
        self._outer = tk.Frame(parent, width=panel_width)
        self.frame = tk.LabelFrame(
            self._outer,
            text="EEG Lead-Off",
            font=("Arial", 11, "bold"),
            padx=6,
            pady=4,
        )
        self.frame.pack(fill=tk.BOTH, expand=True)
        row = tk.Frame(self.frame)
        row.pack(anchor="center")

        self._led_items: dict[str, tuple[tk.Canvas, int]] = {}
        for idx, (key, _bit, label) in enumerate(LEAD_OFF_ELECTRODES):
            cell = tk.Frame(row)
            cell.grid(row=0, column=idx, padx=6, pady=3, sticky="w")

            canvas = tk.Canvas(cell, width=18, height=18, highlightthickness=0, bd=0)
            canvas.pack(side=tk.LEFT)
            led_id = canvas.create_oval(2, 2, 16, 16, fill=COLOR_UNKNOWN, outline="#424242")
            tk.Label(cell, text=label, font=("Arial", 10)).pack(side=tk.LEFT, padx=(4, 0))
            self._led_items[key] = (canvas, led_id)

        self._raw_label = tk.Label(
            self.frame,
            text="BIN: ----   HEX: --",
            font=("Arial", 9),
            fg="#616161",
        )
        self._raw_label.pack(anchor="center", pady=(2, 0))

        self._outer.update_idletasks()
        self._outer.config(height=self.frame.winfo_reqheight())
        self._outer.pack_propagate(False)

    def pack(self, **kwargs) -> None:
        self._outer.pack(**kwargs)

    def reset(self) -> None:
        for key in self._led_items:
            self._set_color(key, COLOR_UNKNOWN)
        self._raw_label.config(text="BIN: ----   HEX: --")

    def update_electrodes(self, electrodes: dict[str, bool], lead_off_raw: int) -> None:
        """electrodes: True=lead-off(빨강), False=lead-on(초록)."""
        value = lead_off_raw & 0x0F
        self._raw_label.config(text=f"BIN: 0b{value:04b}   HEX: 0x{value:02X}")
        for key, is_off in electrodes.items():
            if key not in self._led_items:
                continue
            color = COLOR_LEAD_OFF if is_off else COLOR_CONTACT
            self._set_color(key, color)

    def _set_color(self, key: str, color: str) -> None:
        canvas, led_id = self._led_items[key]
        canvas.itemconfig(led_id, fill=color)
