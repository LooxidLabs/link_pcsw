"""LINKBAND PC SW entry point."""
from pathlib import Path
import sys
import tkinter as tk

# `python app/main.py`로 직접 실행될 때도 패키지 import가 되도록 루트 경로를 보정.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import state
from app.ui.app import App


def main() -> int:
    root = tk.Tk()
    state.global_main_root = root
    app = App(root)
    state.global_app = app
    app.start_ble_scan_startup()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
