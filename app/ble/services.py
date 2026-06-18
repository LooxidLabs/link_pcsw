"""BLE service toggle handlers."""
import asyncio

from app import state
from app import constants
from app.ble import callbacks

def toggle_accelerometer(self):
    if state.global_ble_client is None or state.global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.accelerometer_running:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.start_notify(constants.ACCELEROMETER_CHAR_UUID, callbacks.accelerometer_callback),
                state.global_ble_loop)
            future.result()
            self.accelerometer_running = True
            self.accelerometer_button.config(text="Accelerometer Stop")            
            self.add_message("Accelerometer Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.stop_notify(constants.ACCELEROMETER_CHAR_UUID),
                state.global_ble_loop)
            future.result()
            self.accelerometer_running = False
            self.accelerometer_button.config(text="Accelerometer Start")            
            self.add_message("Accelerometer Stopped")
    except Exception as e:        
        self.add_message("Accelrometer error: {e}")
        

def toggle_battery(self):
    if state.global_ble_client is None or state.global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.battery_running:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.start_notify(constants.BATTERY_CHAR_UUID, callbacks.battery_callback),
                state.global_ble_loop)
            future.result()
            self.battery_running = True
            self.battery_button.config(text="Battery Stop")
            self.add_message("Battery Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.stop_notify(constants.BATTERY_CHAR_UUID),
                state.global_ble_loop)
            future.result()
            self.battery_running = False
            self.battery_button.config(text="Battery Start")
            self.add_message("Battery Stoppped")
    except Exception as e:
        self.add_message("Battery error: {e}")

def toggle_eeg_write(self):
    if state.global_ble_client is None or state.global_ble_loop is None:        
        self.add_message("BLE not connected")
        return
    try:
        if not self.eeg_write_running:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.write_gatt_char(constants.EEG_WRITE_CHAR_UUID, b'start'),
                state.global_ble_loop)
            future.result()
            self.eeg_write_running = True
            self.eeg_write_button.config(text="EEG Write Stop")            
            self.add_message("EEG Write 'start' sent")
        else:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.write_gatt_char(constants.EEG_WRITE_CHAR_UUID, b'stop'),
                state.global_ble_loop)
            future.result()
            self.eeg_write_running = False
            self.eeg_write_button.config(text="EEG Write Start")            
            self.add_message("EEG Write 'stop' sent")
    except Exception as e:        
        self.add_message("EEG Write error: {e}")

def toggle_eeg_notify(self):
    if state.global_ble_client is None or state.global_ble_loop is None:
        self.add_message("BLE not connected")
        return
    try:
        if not self.eeg_notify_running:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.start_notify(constants.EEG_NOTIFY_CHAR_UUID, callbacks.eeg_notify_callback),
                state.global_ble_loop)
            future.result()
            self.eeg_notify_running = True
            self.eeg_notify_button.config(text="EEG Notify Stop")            
            self.add_message("EEG Notify Running")
        else:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.stop_notify(constants.EEG_NOTIFY_CHAR_UUID),
                state.global_ble_loop)
            future.result()
            self.eeg_notify_running = False
            self.eeg_notify_button.config(text="EEG Notify Start")
            self.add_message("EEG Notify Stopped")
            state.reset_eeg_lead_off()
    except Exception as e:
        self.add_message(f"EEG Notify error: {e}")

def toggle_ppg(self):
    if state.global_ble_client is None or state.global_ble_loop is None:
        self.add_message("BLE not connected")
        return
    try:
        if not self.ppg_running:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.start_notify(constants.PPG_CHAR_UUID, callbacks.ppg_callback),
                state.global_ble_loop)
            future.result()
            self.ppg_running = True
            self.ppg_button.config(text="PPG Stop")
            self.add_message("PPG Running")
            self.update_bpm()
        else:
            future = asyncio.run_coroutine_threadsafe(
                state.global_ble_client.stop_notify(constants.PPG_CHAR_UUID),
                state.global_ble_loop)
            future.result()
            self.ppg_running = False
            self.ppg_button.config(text="PPG Start")
            self.add_message("PPG Stopped")
            state.data_buffer["ppg"].clear()
    except Exception as e:
        self.add_message(f"PPG error: {e}")
