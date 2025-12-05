# /app/mppt_register_map.py
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------
# 📌 佛山金廣源 Ampinvt MPPT V1.1 - 寄存器映射表 (功率計算版)
# ------------------------------------------------------------------

B3_REALTIME = [] 

# ✅ B1：完整數據 (93 Bytes)
B1_INFO = [
    # --- 系統參數 ---
    {"key": "battery_type", "name": "電池類型代碼", "unit": None, "scale": 1, "offset": 8, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:battery-unknown"}},
    {"key": "battery_count", "name": "電池數量", "unit": "pcs", "scale": 1, "offset": 10, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:battery-plus"}},
    
    # --- 設定值 (Scale 100) ---
    {"key": "rated_voltage", "name": "額定電壓設定", "unit": "V", "scale": 100, "offset": 16, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "equalize_voltage", "name": "均充電壓設定", "unit": "V", "scale": 100, "offset": 18, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "float_voltage", "name": "浮充電壓設定", "unit": "V", "scale": 100, "offset": 20, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "max_charge_current", "name": "設置最大充電電流", "unit": "A", "scale": 100, "offset": 26, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current"}},

    # --- 實時測量值 ---
    {"key": "pv_voltage", "name": "PV 電壓", "unit": "V", "scale": 10, "offset": 30, "length": 2, "signed": False, 
     "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}},
    
    {"key": "battery_voltage", "name": "電池電壓", "unit": "V", "scale": 100, "offset": 32, "length": 2, "signed": False, 
     "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}},
    
    {"key": "charge_current", "name": "充電電流", "unit": "A", "scale": 100, "offset": 34, "length": 2, "signed": False, 
     "ha": {"type": "sensor", "device_class": "current", "state_class": "measurement"}},
    
    # ✅ [新增] 瞬時充電功率 (將在 mqtt_client 中計算)
    # Offset 999 確保 main.py 的解碼器會跳過它
    {"key": "charge_power", "name": "瞬時充電功率", "unit": "W", "scale": 1, "offset": 999, "length": 0, "signed": False, 
     "ha": {"type": "sensor", "device_class": "power", "state_class": "measurement"}},

    {"key": "internal_temp_1", "name": "內部溫度 1", "unit": "°C", "scale": 10, "offset": 36, "length": 2, "signed": True, 
     "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"}},
    
    {"key": "external_temp_1", "name": "外部溫度 1", "unit": "°C", "scale": 100, "offset": 40, "length": 2, "signed": True, 
     "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"}},

    # --- 發電量 ---
    {"key": "today_yield_wh", "name": "今日發電量", "unit": "Wh", "scale": 1, "offset": 44, "length": 4, "signed": False, 
     "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}},
    
    {"key": "total_yield_wh", "name": "總發電量", "unit": "Wh", "scale": 1, "offset": 48, "length": 4, "signed": False, 
     "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}},
]

# ✅ 狀態位元
B1_STATUS_BITS = {
    "run_status":       {"byte": 3, "bit": 0, "name": "運行狀態", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "fan_status":       {"byte": 3, "bit": 2, "name": "風扇狀態", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "temp_status":      {"byte": 3, "bit": 3, "name": "溫度保護啟用", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "int_temp1_fault":  {"byte": 3, "bit": 5, "name": "內部溫度1異常", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "charging":         {"byte": 4, "bit": 0, "name": "充電中", "ha": {"type": "binary_sensor", "device_class": "battery_charging"}},
    "equalizing_charge":{"byte": 4, "bit": 1, "name": "均充中", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "tracking":         {"byte": 4, "bit": 2, "name": "MPPT 追蹤中", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "float_charge":     {"byte": 4, "bit": 3, "name": "浮充中", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "charge_limited":   {"byte": 4, "bit": 4, "name": "充電限流", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "pv_over_voltage":  {"byte": 4, "bit": 7, "name": "PV 過壓警告", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "load_output":      {"byte": 5, "bit": 1, "name": "負載輸出", "ha": {"type": "binary_sensor", "device_class": "running"}},
    "overcharge_protect":{"byte": 5, "bit": 4, "name": "過充保護啟用", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "overvoltage_protect":{"byte": 5, "bit": 5, "name": "過壓保護", "ha": {"type": "binary_sensor", "device_class": "problem"}},
}

B3_STATUS_BITS = B1_STATUS_BITS

C0_COMMANDS = {
    0x01: {"key": "allow_charge", "name": "允許充電"},
    0x02: {"key": "disable_charge", "name": "禁止充電"},
    0x03: {"key": "dc_on", "name": "遠程開啟DC輸出"},
    0x04: {"key": "dc_off", "name": "遠程關閉DC輸出"},
}

D0_PARAMS = {
    0x09: {"key": "set_battery_type", "name": "電池類型", "data_len": 1, "scale": 1, "valid_bytes": [6]},
    0x21: {"key": "set_equalize_voltage", "name": "均充電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6]},
}

CLOCK_SET = {"year": 2, "month": 3, "day": 4, "hour": 5, "minute": 6}
