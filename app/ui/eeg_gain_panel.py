"""EEG PGA Gain 선택 UI (Lead-Off 패널 옆)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from app import constants


class EegGainPanel:
    """PGA Gain 8 / 12 — EEG Notify·레코딩 중 변경 불가."""

    def __init__(
        self,
        parent: tk.Misc,
        on_gain_change: Callable[[int], None],
        width: int | None = None,
    ) -> None:
        panel_width = width if width is not None else constants.EEG_GAIN_PANEL_WIDTH_PX
        self._on_gain_change = on_gain_change
        self._outer = tk.Frame(parent, width=panel_width)
        self.frame = tk.LabelFrame(
            self._outer,
            text="EEG PGA Gain",
            font=("Arial", 11, "bold"),
            padx=6,
            pady=4,
        )
        self.frame.pack(fill=tk.BOTH, expand=True)

        row = tk.Frame(self.frame)
        row.pack(anchor="center", pady=2)

        self._gain_var = tk.IntVar(value=constants.EEG_PGA_GAIN_DEFAULT)
        self._radios: list[tk.Radiobutton] = []
        for idx, gain in enumerate(constants.EEG_PGA_GAIN_OPTIONS):
            rb = tk.Radiobutton(
                row,
                text=str(gain),
                variable=self._gain_var,
                value=gain,
                font=("Arial", 10),
                command=self._emit_gain_change,
            )
            rb.pack(side=tk.LEFT, padx=(0 if idx == 0 else 12, 0))
            self._radios.append(rb)

        self._outer.update_idletasks()
        self._outer.config(height=self.frame.winfo_reqheight())
        self._outer.pack_propagate(False)

    def pack(self, **kwargs) -> None:
        self._outer.pack(**kwargs)

    def set_gain(self, gain: int, notify: bool = False) -> None:
        if gain in constants.EEG_PGA_GAIN_OPTIONS:
            self._gain_var.set(gain)
            if notify:
                self._on_gain_change(gain)

    def set_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for rb in self._radios:
            rb.config(state=state)

    def _emit_gain_change(self) -> None:
        self._on_gain_change(int(self._gain_var.get()))
