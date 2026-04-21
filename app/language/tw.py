# /app/mppt_map_tw.py
# -*- coding: utf-8 -*-
# 📌 佛山金廣源 Ampinvt MPPT - 繁體中文地圖 (Traditional Chinese)
# 🔥 V2.1 版面淨化版：加入 entity_category，收斂實體避免污染 Dashboard

B1_INFO = [
    # ── 設備設定參數 (Diagnostic) ──────────────────────────────
    {
        "key": "battery_type", "name": "電池類型",
        "unit": None, "scale": 1, "offset": 8, "length": 1, "signed": False,
        "map": {0: "鉛酸(免維護)", 1: "鉛酸(膠體)", 2: "鉛酸(液體)", 3: "鋰電池"},
        "ha": {"type": "sensor", "icon": "mdi:car-battery", "entity_category": "diagnostic"}
    },
    {
        "key": "recognition_mode", "name": "識別方式",
        "unit": None, "scale": 1, "offset": 9, "length": 1, "signed": False,
        "map": {0: "自動識別", 1: "手動設定", 2: "手動(24V)", 3: "手動(36V)",
                4: "手動(48V)", 5: "手動(60V)", 6: "手動(72V)", 7: "手動(84V)", 8: "手動(96V)"},
        "ha": {"type": "sensor", "icon": "mdi:eye-refresh", "entity_category": "diagnostic"}
    },
    {
        "key": "battery_count", "name": "電池串數",
        "unit": "串", "scale": 1, "offset": 10, "length": 1, "signed": False,
        "ha": {"type": "sensor", "icon": "mdi:battery-plus", "entity_category": "diagnostic"}
    },
    {
        "key": "load_control_mode", "name": "負載控制模式",
        "unit": None, "scale": 1, "offset": 11, "length": 1, "signed": False,
        "map": {0: "關閉", 1: "自動(光控+時控)", 2: "時間控制", 3: "光控模式", 4: "遠程控制"},
        "ha": {"type": "sensor", "icon": "mdi:cog-transfer", "entity_category": "diagnostic"}
    },
    {
        "key": "device_addr", "name": "設備通訊地址",
        "unit": None, "scale": 1, "offset": 12, "length": 1, "signed": False,
        "ha": {"type": "sensor", "icon": "mdi:identifier", "entity_category": "diagnostic"}
    },
    {
        "key": "baud_rate", "name": "通訊波特率",
        "unit": None, "scale": 1, "offset": 13, "length": 1, "signed": False,
        "map": {1: "1200", 2: "2400", 3: "4800", 4: "9600"},
        "ha": {"type": "sensor", "icon": "mdi:speedometer", "entity_category": "diagnostic"}
    },

    # ── 電壓電流設定參數 (Diagnostic) ─────────────────────────
    {
        "key": "rated_voltage", "name": "系統額定電壓",
        "unit": "V", "scale": 100, "offset": 16, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "equalize_voltage", "name": "均充電壓設定",
        "unit": "V", "scale": 100, "offset": 18, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "float_voltage", "name": "浮充電壓設定",
        "unit": "V", "scale": 100, "offset": 20, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "discharge_limit_voltage", "name": "放電電壓下限",
        "unit": "V", "scale": 100, "offset": 22, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "hw_max_charge_current", "name": "硬體最大充電電流",
        "unit": "A", "scale": 100, "offset": 24, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "current", "icon": "mdi:current-dc", "entity_category": "diagnostic"}
    },
    {
        "key": "max_charge_current", "name": "設定最大充電電流",
        "unit": "A", "scale": 100, "offset": 26, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "current", "entity_category": "diagnostic"}
    },
    {
        "key": "run_charge_current_limit", "name": "運行充電電流限制",
        "unit": "A", "scale": 100, "offset": 28, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "current", "entity_category": "diagnostic"}
    },

    # ── 即時運行數據 (Main Dashboard，不加 entity_category) ──────────
    {
        "key": "pv_voltage", "name": "PV 輸入電壓",
        "unit": "V", "scale": 10, "offset": 30, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}
    },
    {
        "key": "battery_voltage", "name": "電池實時電壓",
        "unit": "V", "scale": 100, "offset": 32, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}
    },
    {
        "key": "charge_current", "name": "實時充電電流",
        "unit": "A", "scale": 100, "offset": 34, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "current", "state_class": "measurement"}
    },
    {
        "key": "charge_power", "name": "瞬時充電功率",
        "unit": "W", "scale": 1, "offset": 999, "length": 0, "signed": False,
        "ha": {"type": "sensor", "device_class": "power", "state_class": "measurement"}
    },
    # 溫度視為健康診斷指標，隱藏進 Diagnostic
    {
        "key": "internal_temp_1", "name": "設備內部溫度",
        "unit": "°C", "scale": 10, "offset": 36, "length": 2, "signed": True,
        "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement", "entity_category": "diagnostic"}
    },
    {
        "key": "external_temp_1", "name": "外部(電池)溫度",
        "unit": "°C", "scale": 100, "offset": 40, "length": 2, "signed": True,
        "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement", "entity_category": "diagnostic"}
    },
    # 發電量放主頁
    {
        "key": "today_yield_wh", "name": "今日發電量",
        "unit": "Wh", "scale": 1, "offset": 44, "length": 4, "signed": False,
        "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}
    },
    {
        "key": "total_yield_wh", "name": "累計總發電量",
        "unit": "Wh", "scale": 1, "offset": 48, "length": 4, "signed": False,
        "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}
    },

    # ── 型號 & 進階設定 (Diagnostic) ──────────────────────────
    {
        "key": "model_code", "name": "型號編碼",
        "unit": None, "scale": 1, "offset": 52, "length": 1, "signed": False,
        "ha": {"type": "sensor", "icon": "mdi:barcode", "entity_category": "diagnostic"}
    },
    {
        "key": "time_ctrl_flag", "name": "時控組啟用標志",
        "unit": None, "scale": 1, "offset": 53, "length": 1, "signed": False,
        "map": {0: "全部關閉", 1: "開啟組1", 2: "開啟組2", 3: "全部開啟"}, 
        "ha": {"type": "sensor", "icon": "mdi:clock-check", "entity_category": "diagnostic"}
    },
    {
        "key": "discharge_recovery_voltage", "name": "過放恢復電壓",
        "unit": "V", "scale": 100, "offset": 54, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "over_voltage_protection", "name": "過壓保護電壓",
        "unit": "V", "scale": 100, "offset": 56, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "over_voltage_recovery", "name": "過壓恢復電壓",
        "unit": "V", "scale": 100, "offset": 58, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "light_control_on_voltage", "name": "光控開啟電壓",
        "unit": "V", "scale": 1, "offset": 60, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "light_control_off_voltage", "name": "光控關閉電壓",
        "unit": "V", "scale": 1, "offset": 62, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "entity_category": "diagnostic"}
    },
    {
        "key": "light_control_on_delay", "name": "光控開啟延遲",
        "unit": "s", "scale": 1, "offset": 64, "length": 2, "signed": False,
        "ha": {"type": "sensor", "icon": "mdi:timer-sand", "entity_category": "diagnostic"}
    },
    {
        "key": "light_control_off_delay", "name": "光控關閉延遲",
        "unit": "s", "scale": 1, "offset": 66, "length": 2, "signed": False,
        "ha": {"type": "sensor", "icon": "mdi:timer-sand", "entity_category": "diagnostic"}
    },

    # ── 時控時間設定 (Diagnostic) ──────────────────────────────
    {
        "key": "time1_on", "name": "時控1開啟時間",
        "unit": None, "scale": 1, "offset": 68, "length": 4, "signed": False,
        "bcd_time": True,
        "ha": {"type": "sensor", "icon": "mdi:clock-start", "entity_category": "diagnostic"}
    },
    {
        "key": "time1_off", "name": "時控1關閉時間",
        "unit": None, "scale": 1, "offset": 72, "length": 4, "signed": False,
        "bcd_time": True,
        "ha": {"type": "sensor", "icon": "mdi:clock-end", "entity_category": "diagnostic"}
    },
    {
        "key": "time2_on", "name": "時控2開啟時間",
        "unit": None, "scale": 1, "offset": 76, "length": 4, "signed": False,
        "bcd_time": True,
        "ha": {"type": "sensor", "icon": "mdi:clock-start", "entity_category": "diagnostic"}
    },
    {
        "key": "time2_off", "name": "時控2關閉時間",
        "unit": None, "scale": 1, "offset": 80, "length": 4, "signed": False,
        "bcd_time": True,
        "ha": {"type": "sensor", "icon": "mdi:clock-end", "entity_category": "diagnostic"}
    },
]


# ═══════════════════════════════════════════════════════════════
# B1 / B3 狀態位元地圖（全部隱藏為 Diagnostic）
# ═══════════════════════════════════════════════════════════════
B1_STATUS_BITS = {
    # ── Byte 3：運行狀態 ──────────────────────────────────────
    "run_status":           {"byte": 3, "bit": 0, "name": "運行異常",        "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "battery_overdischarge":{"byte": 3, "bit": 1, "name": "電池過放保護",    "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "fan_fault":            {"byte": 3, "bit": 2, "name": "風扇故障",        "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "overtemp":             {"byte": 3, "bit": 3, "name": "過溫保護",        "ha": {"type": "binary_sensor", "device_class": "heat", "entity_category": "diagnostic"}},
    "dc_short_circuit":     {"byte": 3, "bit": 4, "name": "DC輸出短路保護",  "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "internal_temp1_fault": {"byte": 3, "bit": 5, "name": "內部溫度1故障",   "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "internal_temp2_fault": {"byte": 3, "bit": 6, "name": "內部溫度2故障",   "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "external_temp1_fault": {"byte": 3, "bit": 7, "name": "外部溫度1故障",   "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},

    # ── Byte 4：充電狀態 ──────────────────────────────────────
    "charging":             {"byte": 4, "bit": 0, "name": "充電中",          "ha": {"type": "binary_sensor", "device_class": "battery_charging", "entity_category": "diagnostic"}},
    "equalizing":           {"byte": 4, "bit": 1, "name": "均充中",          "ha": {"type": "binary_sensor", "device_class": "battery_charging", "entity_category": "diagnostic"}},
    "tracking":             {"byte": 4, "bit": 2, "name": "MPPT跟踪中",      "ha": {"type": "binary_sensor", "device_class": "running", "entity_category": "diagnostic"}},
    "floating":             {"byte": 4, "bit": 3, "name": "浮充中",          "ha": {"type": "binary_sensor", "device_class": "battery_charging", "entity_category": "diagnostic"}},
    "charge_limiting":      {"byte": 4, "bit": 4, "name": "充電限流中",      "ha": {"type": "binary_sensor", "device_class": "running", "entity_category": "diagnostic"}},
    "charge_derating":      {"byte": 4, "bit": 5, "name": "充電降額中",      "ha": {"type": "binary_sensor", "device_class": "running", "entity_category": "diagnostic"}},
    "remote_charge_disable":{"byte": 4, "bit": 6, "name": "遠程禁止充電",    "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "pv_overvoltage":       {"byte": 4, "bit": 7, "name": "PV過壓",          "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},

    # ── Byte 5：控制狀態 ──────────────────────────────────────
    "charge_relay":         {"byte": 5, "bit": 0, "name": "充電繼電器",      "ha": {"type": "binary_sensor", "device_class": "power", "entity_category": "diagnostic"}},
    "load_output":          {"byte": 5, "bit": 1, "name": "負載輸出",        "ha": {"type": "binary_sensor", "device_class": "power", "entity_category": "diagnostic"}},
    "fan_running":          {"byte": 5, "bit": 2, "name": "風扇運行中",      "ha": {"type": "binary_sensor", "device_class": "running", "entity_category": "diagnostic"}},
    "overcharge_protect":   {"byte": 5, "bit": 4, "name": "過充保護",        "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
    "overvoltage_protect":  {"byte": 5, "bit": 5, "name": "過壓保護",        "ha": {"type": "binary_sensor", "device_class": "problem", "entity_category": "diagnostic"}},
}
B3_STATUS_BITS = B1_STATUS_BITS


# ═══════════════════════════════════════════════════════════════
# B3 (0xB3) 僅查詢即時數據 
# ═══════════════════════════════════════════════════════════════
B3_REALTIME = [
    {
        "key": "pv_voltage", "name": "PV 輸入電壓",
        "unit": "V", "scale": 10, "offset": 6, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}
    },
    {
        "key": "battery_voltage", "name": "電池實時電壓",
        "unit": "V", "scale": 100, "offset": 8, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"}
    },
    {
        "key": "charge_current", "name": "實時充電電流",
        "unit": "A", "scale": 100, "offset": 10, "length": 2, "signed": False,
        "ha": {"type": "sensor", "device_class": "current", "state_class": "measurement"}
    },
    {
        "key": "internal_temp_1", "name": "設備內部溫度",
        "unit": "°C", "scale": 10, "offset": 12, "length": 2, "signed": True,
        "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement", "entity_category": "diagnostic"}
    },
    {
        "key": "external_temp_1", "name": "外部(電池)溫度",
        "unit": "°C", "scale": 100, "offset": 16, "length": 2, "signed": True,
        "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement", "entity_category": "diagnostic"}
    },
    {
        "key": "today_yield_wh", "name": "今日發電量",
        "unit": "Wh", "scale": 1, "offset": 20, "length": 4, "signed": False,
        "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}
    },
    {
        "key": "total_yield_wh", "name": "累計總發電量",
        "unit": "Wh", "scale": 1, "offset": 24, "length": 4, "signed": False,
        "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"}
    },
]


# ═══════════════════════════════════════════════════════════════
# 控制開關（主頁面顯示，不加分類）
# ═══════════════════════════════════════════════════════════════

CONTROL_SWITCHES = {
    "charge_enable": {
        "name": "充電功能開關",
        "on_code": 0x01, "off_code": 0x02,
        "icon": "mdi:battery-check",
        "state_key": "charge_relay",
        "ha": {"type": "switch"}
    },
    "load_enable": {
        "name": "負載輸出開關",
        "on_code": 0x03, "off_code": 0x04,
        "icon": "mdi:power-socket-eu",
        "state_key": "load_output",
        "ha": {"type": "switch"}
    }
}

CONTROL_BUTTONS = {
    "alarm_mute":   {"name": "蜂鳴器消音",      "code": 0x05, "icon": "mdi:volume-off",       "ha": {"type": "button", "entity_category": "config"}},
    "backlight_on": {"name": "開啟背光(1min)",   "code": 0x06, "icon": "mdi:monitor-shimmer",   "ha": {"type": "button", "entity_category": "config"}},
    "sync_time":    {"name": "同步系統時間",      "code": 0xDF, "icon": "mdi:clock-check",       "ha": {"type": "button", "entity_category": "config"}}
}


# ═══════════════════════════════════════════════════════════════
# 參數設定（全部歸入 Config）
# ═══════════════════════════════════════════════════════════════

D0_PARAMS = {
    0x09: {
        "key": "set_battery_type", "name": "設定-電池類型",
        "data_len": 1, "scale": 1, "valid_bytes": [6],
        "ha": {"type": "select",
               "options": ["鉛酸(免維護)", "鉛酸(膠體)", "鉛酸(液體)", "鋰電池"],
               "icon": "mdi:car-battery", "link_b1": "battery_type", "entity_category": "config"}
    },
    0x0A: {
        "key": "set_battery_count", "name": "設定-電池串數",
        "data_len": 1, "scale": 1, "valid_bytes": [6],
        "ha": {"type": "number", "min": 1, "max": 16, "step": 1,
               "mode": "box", "icon": "mdi:battery-plus", "link_b1": "battery_count", "entity_category": "config"}
    },
    0x0B: {
        "key": "set_recognition_mode", "name": "設定-識別方式",
        "data_len": 1, "scale": 1, "valid_bytes": [6],
        "ha": {"type": "select", 
               "options": ["自動識別", "手動設定", "手動(24V)", "手動(36V)", "手動(48V)", "手動(60V)", "手動(72V)", "手動(84V)", "手動(96V)"],
               "icon": "mdi:eye-settings", "link_b1": "recognition_mode", "entity_category": "config"}
    },
    0x0C: {
        "key": "set_load_mode", "name": "設定-負載模式",
        "data_len": 1, "scale": 1, "valid_bytes": [6],
        "ha": {"type": "select",
               "options": ["關閉", "自動(光控+時控)", "時間控制", "光控模式", "遠程控制"],
               "icon": "mdi:cog-transfer", "link_b1": "load_control_mode", "entity_category": "config"}
    },
    0x12: {
        "key": "set_time_ctrl_flag", "name": "設定-時控組開關",
        "data_len": 1, "scale": 1, "valid_bytes": [6],
        "ha": {"type": "select",
               "options": ["全部關閉", "開啟組1", "開啟組2", "全部開啟"],
               "icon": "mdi:clock-check", "link_b1": "time_ctrl_flag", "entity_category": "config"}
    },
    0x21: {
        "key": "set_equalize_voltage", "name": "設定-均充電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 10.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "equalize_voltage", "entity_category": "config"}
    },
    0x22: {
        "key": "set_float_voltage", "name": "設定-浮充電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 10.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "float_voltage", "entity_category": "config"}
    },
    0x23: {
        "key": "set_discharge_limit", "name": "設定-放電下限電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 9.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "discharge_limit_voltage", "entity_category": "config"}
    },
    0x25: {
        "key": "set_max_charge_curr", "name": "設定-最大充電電流",
        "unit": "A", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "min": 0.0, "max": 60.0,
               "step": 1.0, "mode": "slider", "link_b1": "max_charge_current", "entity_category": "config"}
    },
    0x26: {
        "key": "set_discharge_recover", "name": "設定-過放恢復電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 10.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "discharge_recovery_voltage", "entity_category": "config"}
    },
    0x27: {
        "key": "set_over_prot_vol", "name": "設定-過壓保護電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 12.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "over_voltage_protection", "entity_category": "config"}
    },
    0x28: {
        "key": "set_over_recover_vol", "name": "設定-過壓恢復電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0,
               "li_base_min": 12.0, "li_base_max": 14.6,
               "step": 0.1, "mode": "box", "link_b1": "over_voltage_recovery", "entity_category": "config"}
    },
    0x29: {
        "key": "set_light_on_vol", "name": "設定-光控開啟電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "min": 0.0, "max": 50.0,
               "step": 1.0, "mode": "box", "link_b1": "light_control_on_voltage", "entity_category": "config"}
    },
    0x2A: {
        "key": "set_light_off_vol", "name": "設定-光控關閉電壓",
        "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6],
        "ha": {"type": "number", "min": 0.0, "max": 50.0,
               "step": 1.0, "mode": "box", "link_b1": "light_control_off_voltage", "entity_category": "config"}
    },
    0x2B: {
        "key": "set_light_on_delay", "name": "設定-光控開啟延遲",
        "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6],
        "ha": {"type": "number", "min": 0, "max": 999,
               "step": 1, "mode": "box", "link_b1": "light_control_on_delay", "entity_category": "config"}
    },
    0x2C: {
        "key": "set_light_off_delay", "name": "設定-光控關閉延遲",
        "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6],
        "ha": {"type": "number", "min": 0, "max": 999,
               "step": 1, "mode": "box", "link_b1": "light_control_off_delay", "entity_category": "config"}
    },
    0x2D: {
        "key": "set_time1_on", "name": "設定-時控1開啟時間",
        "data_len": 4, "scale": 1, "valid_bytes": [3, 4, 5, 6],
        "bcd_time": True,
        "ha": {"type": "text", "icon": "mdi:clock-start",
               "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "link_b1": "time1_on", "entity_category": "config"}
    },
    0x2E: {
        "key": "set_time1_off", "name": "設定-時控1關閉時間",
        "data_len": 4, "scale": 1, "valid_bytes": [3, 4, 5, 6],
        "bcd_time": True,
        "ha": {"type": "text", "icon": "mdi:clock-end",
               "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "link_b1": "time1_off", "entity_category": "config"}
    },
    0x2F: {
        "key": "set_time2_on", "name": "設定-時控2開啟時間",
        "data_len": 4, "scale": 1, "valid_bytes": [3, 4, 5, 6],
        "bcd_time": True,
        "ha": {"type": "text", "icon": "mdi:clock-start",
               "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "link_b1": "time2_on", "entity_category": "config"}
    },
    0x30: {
        "key": "set_time2_off", "name": "設定-時控2關閉時間",
        "data_len": 4, "scale": 1, "valid_bytes": [3, 4, 5, 6],
        "bcd_time": True,
        "ha": {"type": "text", "icon": "mdi:clock-end",
               "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "link_b1": "time2_off", "entity_category": "config"}
    },
}

CLOCK_SET = {"year": 2, "month": 3, "day": 4, "hour": 5, "minute": 6}
