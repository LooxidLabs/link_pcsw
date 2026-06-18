"""BLE scan and connection."""
import asyncio
import threading

from bleak import BleakClient, BleakScanner

from app import state
from app import constants
from app.ble import callbacks

async def scan_ble_devices(filter_lxb_only=False):
    devices = await BleakScanner.discover()
    if filter_lxb_only:
        # LXB로 시작하는 디바이스만 필터링
        filtered_devices = [dev for dev in devices if dev.name and dev.name.startswith('LXB')]
        return filtered_devices
    return devices

async def connect_ble(device_address):
    client = BleakClient(device_address)
    try:
        state.debug_log(f"connect_ble: connecting to {device_address!r}")
        await client.connect()
        state.global_ble_client = client
        state.global_ble_loop = asyncio.get_running_loop()
        state.debug_log(f"connect_ble: GATT 세션 시작됨 ({device_address!r})")
        #print("BLE device connected successfully")
        state._run_on_ui(lambda: state.global_app.add_message("BLE device connected successfully"))
        # 연결 직후 표준 Battery Level(0x2A19) GATT Read — Notify 없이 즉시 % 표시
        try:
            bat_data = await client.read_gatt_char(constants.BATTERY_CHAR_UUID)
            battery_level = int.from_bytes(bat_data, byteorder="little")
            callbacks._schedule_battery_label(battery_level)
        except Exception as read_err:
            def _battery_read_fail(err=read_err):
                state.global_app.battery_info_label.config(text="Battery Info: N/A")
                state.global_app.add_message(f"Battery read on connect: {err}")

            state._run_on_ui(_battery_read_fail)
        state.disconnect_requested = False
        # 자동 테스트: 연결 완료 후 메인 스레드에서 Start All Sensors 실행
        if state.global_app is not None and getattr(state.global_app, "_auto_test_want_start_sensors", False):
            state.global_app._auto_test_want_start_sensors = False
            state._run_on_ui_after(500, state.global_app.start_all_sensors)
            state._run_on_ui(
                lambda: state.global_app.add_message("[Auto test] Start All Sensors 예약 (0.5초 후)")
            )
        while not state.disconnect_requested:
            await asyncio.sleep(1)
    except Exception as e:
        #print("BLE connection error:", e)
        state.debug_log(f"connect_ble: 실패 — {type(e).__name__}: {e}")
        state._run_on_ui(lambda err=e: state.global_app.add_message(f"BLE connection error: {err}"))
        if state.global_app is not None:
            state.global_app._auto_test_want_start_sensors = False
    finally:
        await client.disconnect()
        state.global_ble_client = None
        #print("BLE device disconnected")
        state._run_on_ui(lambda: state.global_app.add_message("BLE device disconnected"))
        state._run_on_ui(lambda: state.global_app.battery_info_label.config(text="Battery Info: N/A"))

def ble_thread_main(device_address):
    asyncio.run(connect_ble(device_address))


def _scan_ble_async_worker(lxb_filter: bool) -> None:
    try:
        raw = asyncio.run(scan_ble_devices(lxb_filter))
        state._ble_scan_queue.put(("ok", list(raw)))
    except BaseException as e:
        state._ble_scan_queue.put(("err", e))
