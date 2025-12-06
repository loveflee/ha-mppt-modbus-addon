# /app/mppt_register_map.py
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------
# 📌 佛山金廣源 Ampinvt MPPT V1.1 - 寄存器映射表 (V4.5 時間同步版)
# ------------------------------------------------------------------

B3_REALTIME = [] 

# ✅ B1：完整數據
B1_INFO = [
    # --- 系統基礎資訊 ---
    {
        "key": "battery_type", "name": "電池類型", "unit": None, "scale": 1, "offset": 8, "length": 1, "signed": False, 
        "map": { 0: "鉛酸(免維護)", 1: "鉛酸(膠體)", 2: "鉛酸(液體)", 3: "鋰電池" },
        "ha": {"type": "sensor", "icon": "mdi:car-battery"}
    },
    {
        "key": "recognition_mode", "name": "識別方式", "unit": None, "scale": 1, "offset": 9, "length": 1, "signed": False,
        "map": { 0: "自動識別", 1: "手動設定", 2: "手動(24V)", 3: "手動(36V)", 4: "手動(48V)", 5: "手動(60V)", 6: "手動(72V)", 7: "手動(84V)", 8: "手動(96V)" },
        "ha": {"type": "sensor", "icon": "mdi:eye-refresh"}
    },
    {
        "key": "battery_count", "name": "電池串數", "unit": "串", "scale": 1, "offset": 10, "length": 1, "signed": False, 
        "ha": {"type": "sensor", "icon": "mdi:battery-plus"}
    },
    {
        "key": "load_control_mode", "name": "負載控制模式", "unit": None, "scale": 1, "offset": 11, "length": 1, "signed": False, 
        "map": { 0: "關閉", 1: "自動(光控+時控)", 2: "時間控制", 3: "光控模式", 4: "遠程控制" },
        "ha": {"type": "sensor", "icon": "mdi:cog-transfer"}
    },
    {"key": "device_addr", "name": "設備通訊地址", "unit": None, "scale": 1, "offset": 12, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:identifier"}},
    {"key": "baud_rate", "name": "通訊波特率", "unit": None, "scale": 1, "offset": 13, "length": 1, "signed": False, "map": { 1: "1200", 2: "2400", 3: "4800", 4: "9600" }, "ha": {"type": "sensor", "icon": "mdi:speedometer"}},

    # --- 電壓設定參數 ---
    {"key": "rated_voltage", "name": "系統額定電壓", "unit": "V", "scale": 100, "offset": 16, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "equalize_voltage", "name": "均充電壓設定", "unit": "V", "scale": 100, "offset": 18, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "float_voltage", "name": "浮充電壓設定", "unit": "V", "scale": 100, "offset": 20, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "discharge_limit_voltage", "name": "放電電壓下限", "unit": "V", "scale": 100, "offset": 22, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    
    # --- 電流參數 ---
    {
        "key": "hw_max_charge_current", "name": "硬體最大充電電流", "unit": "A", "scale": 100, "offset": 24, "length": 2, "signed": False, 
        # 🟢 [修正] 加上 device_class: current 以確保單位與 Icon 正確顯示
        "ha": {"type": "sensor", "device_class": "current", "icon": "mdi:microchip"}
    },
    {"key": "max_charge_current", "name": "設定最大充電電流", "unit": "A", "scale": 100, "offset": 26, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current"}},
    {"key": "run_charge_current_limit", "name": "運行充電電流限制", "unit": "A", "scale": 100, "offset": 28, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current"}},

    # --- 實時測量值 ---
    {"key": "pv_voltage", "name": "PV 輸入電壓", "unit": "V", "scale": 10, "offset": 30, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}},
    {"key": "battery_voltage", "name": "電池實時電壓", "unit": "V", "scale": 100, "offset": 32, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}},
    {"key": "charge_current", "name": "實時充電電流", "unit": "A", "scale": 100, "offset": 34, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current", "state_class": "measurement"}},
    {"key": "charge_power", "name": "瞬時充電功率", "unit": "W", "scale": 1, "offset": 999, "length": 0, "signed": False, "ha": {"type": "sensor", "device_class": "power", "state_class": "measurement"}},
    
    # --- 溫度與統計 ---
    {"key": "internal_temp_1", "name": "設備內部溫度", "unit": "°C", "scale": 10, "offset": 36, "length": 2, "signed": True, "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"}},
    {"key": "external_temp_1", "name": "外部(電池)溫度", "unit": "°C", "scale": 100, "offset": 40, "length": 2, "signed": True, "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"}},
    {"key": "today_yield_wh", "name": "今日發電量", "unit": "Wh", "scale": 1, "offset": 44, "length": 4, "signed": False, "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}},
    {"key": "total_yield_wh", "name": "累計總發電量", "unit": "Wh", "scale": 1, "offset": 48, "length": 4, "signed": False, "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}},
    
    # --- 保護參數 ---
    {"key": "model_code", "name": "型號編碼", "unit": None, "scale": 1, "offset": 52, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:barcode"}},
    {"key": "discharge_recovery_voltage", "name": "過放恢復電壓", "unit": "V", "scale": 100, "offset": 54, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "over_voltage_protection", "name": "過壓保護電壓", "unit": "V", "scale": 100, "offset": 56, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "over_voltage_recovery", "name": "過壓恢復電壓", "unit": "V", "scale": 100, "offset": 58, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    
    # --- 光控 ---
    {"key": "light_control_on_voltage", "name": "光控開啟電壓", "unit": "V", "scale": 1, "offset": 60, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "light_control_off_voltage", "name": "光控關閉電壓", "unit": "V", "scale": 1, "offset": 62, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"}},
    {"key": "light_control_on_delay", "name": "光控開啟延遲", "unit": "s", "scale": 1, "offset": 64, "length": 2, "signed": False, "ha": {"type": "sensor", "icon": "mdi:timer-sand"}},
    {"key": "light_control_off_delay", "name": "光控關閉延遲", "unit": "s", "scale": 1, "offset": 66, "length": 2, "signed": False, "ha": {"type": "sensor", "icon": "mdi:timer-sand"}},
]

B1_STATUS_BITS = {
    "run_status":       {"byte": 3, "bit": 0, "name": "運行狀態(異常)", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "charging":         {"byte": 4, "bit": 0, "name": "充電狀態", "ha": {"type": "binary_sensor", "device_class": "battery_charging"}},
    "load_output":      {"byte": 5, "bit": 1, "name": "負載輸出狀態", "ha": {"type": "binary_sensor", "device_class": "power"}},
}
B3_STATUS_BITS = B1_STATUS_BITS

CONTROL_SWITCHES = {
    "charge_enable": { "name": "充電功能開關", "on_code": 0x01, "off_code": 0x02, "icon": "mdi:battery-check", "ha": {"type": "switch"} },
    "load_enable": { "name": "負載輸出開關", "on_code": 0x03, "off_code": 0x04, "icon": "mdi:power-socket-eu", "state_key": "load_output", "ha": {"type": "switch"} }
}

CONTROL_BUTTONS = {
    "alarm_mute": { "name": "蜂鳴器消音", "code": 0x05, "icon": "mdi:volume-off", "ha": {"type": "button"} },
    "backlight_on": { "name": "開啟背光(1min)", "code": 0x06, "icon": "mdi:monitor-shimmer", "ha": {"type": "button"} },
    # 🟢 [NEW] 時間同步按鈕
    "sync_time": { "name": "同步系統時間", "code": 0xDF, "icon": "mdi:clock-check", "ha": {"type": "button"} }
}

D0_PARAMS = {
    0x09: { "key": "set_battery_type", "name": "設定-電池類型", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["鉛酸(免維護)", "鉛酸(膠體)", "鉛酸(液體)", "鋰電池"], "icon": "mdi:car-battery", "link_b1": "battery_type" }},
    0x0A: { "key": "set_battery_count", "name": "設定-電池串數", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "number", "min": 1, "max": 16, "step": 1, "mode": "box", "icon": "mdi:battery-plus", "link_b1": "battery_count" }},
    0x0B: { "key": "set_recognition_mode", "name": "設定-識別方式", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["自動識別", "手動設定"], "icon": "mdi:eye-settings", "link_b1": "recognition_mode" }},
    0x0C: { "key": "set_load_mode", "name": "設定-負載模式", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["關閉", "自動(光控+時控)", "時間控制", "光控模式", "遠程控制"], "icon": "mdi:cog-transfer", "link_b1": "load_control_mode" }},
    0x12: { "key": "set_time_ctrl_flag", "name": "設定-時控組開關", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["全部關閉", "開啟組1", "開啟組2", "全部開啟"], "icon": "mdi:clock-check" }},
    
    0x21: { "key": "set_equalize_voltage", "name": "設定-均充電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "equalize_voltage"} },
    0x22: { "key": "set_float_voltage", "name": "設定-浮充電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "float_voltage"} },
    0x23: { "key": "set_discharge_limit", "name": "設定-放電下限電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "discharge_limit_voltage"} },
    0x25: { "key": "set_max_charge_curr", "name": "設定-最大充電電流", "unit": "A", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0.0, "max": 60.0, "step": 1.0, "mode": "slider", "link_b1": "max_charge_current"} },
    0x26: { "key": "set_discharge_recover", "name": "設定-過放恢復電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "discharge_recovery_voltage"} },
    0x27: { "key": "set_over_prot_vol", "name": "設定-過壓保護電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "over_voltage_protection"} },
    0x28: { "key": "set_over_recover_vol", "name": "設定-過壓恢復電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 9.0, "max": 100.0, "step": 0.1, "mode": "box", "link_b1": "over_voltage_recovery"} },
    0x29: { "key": "set_light_on_vol", "name": "設定-光控開啟電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0.0, "max": 50.0, "step": 1.0, "mode": "box", "link_b1": "light_control_on_voltage"} },
    0x2A: { "key": "set_light_off_vol", "name": "設定-光控關閉電壓", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0.0, "max": 50.0, "step": 1.0, "mode": "box", "link_b1": "light_control_off_voltage"} },
    0x2B: { "key": "set_light_on_delay", "name": "設定-光控開啟延遲", "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0, "max": 999, "step": 1, "mode": "box", "link_b1": "light_control_on_delay"} },
    0x2C: { "key": "set_light_off_delay", "name": "設定-光控關閉延遲", "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0, "max": 999, "step": 1, "mode": "box", "link_b1": "light_control_off_delay"} },
}

CLOCK_SET = {"year": 2, "month": 3, "day": 4, "hour": 5, "minute": 6}
