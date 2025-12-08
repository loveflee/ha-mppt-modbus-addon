# /app/mppt_map_en.py
# -*- coding: utf-8 -*-
# 📌 Ampinvt MPPT - Register Map (English)

B3_REALTIME = [] 

B1_INFO = [
    { "key": "battery_type", "name": "Battery Type", "unit": None, "scale": 1, "offset": 8, "length": 1, "signed": False, "map": { 0: "Lead-Acid(Sealed)", 1: "Lead-Acid(Gel)", 2: "Lead-Acid(Flooded)", 3: "Lithium" }, "ha": {"type": "sensor", "icon": "mdi:car-battery"} },
    { "key": "recognition_mode", "name": "Recognition Mode", "unit": None, "scale": 1, "offset": 9, "length": 1, "signed": False, "map": { 0: "Auto", 1: "Manual", 2: "Manual(24V)", 3: "Manual(36V)", 4: "Manual(48V)", 5: "Manual(60V)", 6: "Manual(72V)", 7: "Manual(84V)", 8: "Manual(96V)" }, "ha": {"type": "sensor", "icon": "mdi:eye-refresh"} },
    { "key": "battery_count", "name": "Battery String", "unit": "s", "scale": 1, "offset": 10, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:battery-plus"} },
    { "key": "load_control_mode", "name": "Load Mode", "unit": None, "scale": 1, "offset": 11, "length": 1, "signed": False, "map": { 0: "Off", 1: "Auto(Light+Time)", 2: "Time Control", 3: "Light Control", 4: "Remote Control" }, "ha": {"type": "sensor", "icon": "mdi:cog-transfer"} },
    { "key": "device_addr", "name": "Device Addr", "unit": None, "scale": 1, "offset": 12, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:identifier"} },
    { "key": "baud_rate", "name": "Baud Rate", "unit": None, "scale": 1, "offset": 13, "length": 1, "signed": False, "map": { 1: "1200", 2: "2400", 3: "4800", 4: "9600" }, "ha": {"type": "sensor", "icon": "mdi:speedometer"} },

    { "key": "rated_voltage", "name": "Rated Voltage", "unit": "V", "scale": 100, "offset": 16, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "equalize_voltage", "name": "Equalize Voltage", "unit": "V", "scale": 100, "offset": 18, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "float_voltage", "name": "Float Voltage", "unit": "V", "scale": 100, "offset": 20, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "discharge_limit_voltage", "name": "Discharge Limit", "unit": "V", "scale": 100, "offset": 22, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    
    { "key": "hw_max_charge_current", "name": "HW Max Current", "unit": "A", "scale": 100, "offset": 24, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current", "icon": "mdi:current-dc"} },
    { "key": "max_charge_current", "name": "Set Max Current", "unit": "A", "scale": 100, "offset": 26, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current"} },
    { "key": "run_charge_current_limit", "name": "Run Current Limit", "unit": "A", "scale": 100, "offset": 28, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current"} },

    { "key": "pv_voltage", "name": "PV Voltage", "unit": "V", "scale": 10, "offset": 30, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"} },
    { "key": "battery_voltage", "name": "Battery Voltage", "unit": "V", "scale": 100, "offset": 32, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage", "state_class": "measurement"} },
    { "key": "charge_current", "name": "Charge Current", "unit": "A", "scale": 100, "offset": 34, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "current", "state_class": "measurement"} },
    { "key": "charge_power", "name": "Charge Power", "unit": "W", "scale": 1, "offset": 999, "length": 0, "signed": False, "ha": {"type": "sensor", "device_class": "power", "state_class": "measurement"} },
    
    { "key": "internal_temp_1", "name": "Internal Temp", "unit": "°C", "scale": 10, "offset": 36, "length": 2, "signed": True, "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"} },
    { "key": "external_temp_1", "name": "External Temp", "unit": "°C", "scale": 100, "offset": 40, "length": 2, "signed": True, "ha": {"type": "sensor", "device_class": "temperature", "state_class": "measurement"} },
    { "key": "today_yield_wh", "name": "Today Yield", "unit": "Wh", "scale": 1, "offset": 44, "length": 4, "signed": False, "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"} },
    { "key": "total_yield_wh", "name": "Total Yield", "unit": "Wh", "scale": 1, "offset": 48, "length": 4, "signed": False, "ha": {"type": "sensor", "device_class": "energy", "state_class": "total_increasing"} },
    
    { "key": "model_code", "name": "Model Code", "unit": None, "scale": 1, "offset": 52, "length": 1, "signed": False, "ha": {"type": "sensor", "icon": "mdi:barcode"} },
    { "key": "discharge_recovery_voltage", "name": "Discharge Recovery", "unit": "V", "scale": 100, "offset": 54, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "over_voltage_protection", "name": "Over Volt Prot", "unit": "V", "scale": 100, "offset": 56, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "over_voltage_recovery", "name": "Over Volt Recover", "unit": "V", "scale": 100, "offset": 58, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    
    { "key": "light_control_on_voltage", "name": "Light ON Volt", "unit": "V", "scale": 1, "offset": 60, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "light_control_off_voltage", "name": "Light OFF Volt", "unit": "V", "scale": 1, "offset": 62, "length": 2, "signed": False, "ha": {"type": "sensor", "device_class": "voltage"} },
    { "key": "light_control_on_delay", "name": "Light ON Delay", "unit": "s", "scale": 1, "offset": 64, "length": 2, "signed": False, "ha": {"type": "sensor", "icon": "mdi:timer-sand"} },
    { "key": "light_control_off_delay", "name": "Light OFF Delay", "unit": "s", "scale": 1, "offset": 66, "length": 2, "signed": False, "ha": {"type": "sensor", "icon": "mdi:timer-sand"} },
]

B1_STATUS_BITS = {
    "run_status": {"byte": 3, "bit": 0, "name": "Status", "ha": {"type": "binary_sensor", "device_class": "problem"}},
    "charging": {"byte": 4, "bit": 0, "name": "Charging", "ha": {"type": "binary_sensor", "device_class": "battery_charging"}},
    "load_output": {"byte": 5, "bit": 1, "name": "Load Output", "ha": {"type": "binary_sensor", "device_class": "power"}},
}
B3_STATUS_BITS = B1_STATUS_BITS

CONTROL_SWITCHES = {
    "charge_enable": { "name": "Charge Enable", "on_code": 0x01, "off_code": 0x02, "icon": "mdi:battery-check", "ha": {"type": "switch"} },
    "load_enable": { "name": "Load Enable", "on_code": 0x03, "off_code": 0x04, "icon": "mdi:power-socket-eu", "state_key": "load_output", "ha": {"type": "switch"} }
}

CONTROL_BUTTONS = {
    "alarm_mute": { "name": "Mute Alarm", "code": 0x05, "icon": "mdi:volume-off", "ha": {"type": "button"} },
    "backlight_on": { "name": "Backlight ON", "code": 0x06, "icon": "mdi:monitor-shimmer", "ha": {"type": "button"} },
    "sync_time": { "name": "Sync Time", "code": 0xDF, "icon": "mdi:clock-check", "ha": {"type": "button"} }
}

D0_PARAMS = {
    0x09: { "key": "set_battery_type", "name": "Set Battery Type", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["Lead-Acid(Sealed)", "Lead-Acid(Gel)", "Lead-Acid(Flooded)", "Lithium"], "icon": "mdi:car-battery", "link_b1": "battery_type" }},
    0x0A: { "key": "set_battery_count", "name": "Set Battery String", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "number", "min": 1, "max": 16, "step": 1, "mode": "box", "icon": "mdi:battery-plus", "link_b1": "battery_count" }},
    0x0B: { "key": "set_recognition_mode", "name": "Set Recog Mode", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["Auto", "Manual"], "icon": "mdi:eye-settings", "link_b1": "recognition_mode" }},
    0x0C: { "key": "set_load_mode", "name": "Set Load Mode", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["Off", "Auto", "Time Ctrl", "Light Ctrl", "Remote"], "icon": "mdi:cog-transfer", "link_b1": "load_control_mode" }},
    0x12: { "key": "set_time_ctrl_flag", "name": "Set Timer Flag", "data_len": 1, "scale": 1, "valid_bytes": [6], "ha": { "type": "select", "options": ["All Off", "Group 1", "Group 2", "All On"], "icon": "mdi:clock-check" }},
    
    0x21: { "key": "set_equalize_voltage", "name": "Set Equalize Volt", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 10.0, "li_base_max": 14.6, "step": 0.1, "mode": "box", "link_b1": "equalize_voltage"} },
            
    0x22: { "key": "set_float_voltage", "name": "Set Float Volt", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 10.0, "li_base_max": 14.6, "step": 0.1, "mode": "box", "link_b1": "float_voltage"} },
            
    0x23: { "key": "set_discharge_limit", "name": "Set Disc Limit", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 8.0, "li_base_max": 17.0, "step": 0.1, "mode": "box", "link_b1": "discharge_limit_voltage"} },
            
    0x25: { "key": "set_max_charge_curr", "name": "Set Max Current", "unit": "A", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "min": 0.0, "max": 60.0, "step": 1.0, "mode": "slider", "link_b1": "max_charge_current"} },
            
    0x26: { "key": "set_discharge_recover", "name": "Set Disc Recover", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 9.0, "li_base_max": 18.0, "step": 0.1, "mode": "box", "link_b1": "discharge_recovery_voltage"} },
            
    0x27: { "key": "set_over_prot_vol", "name": "Set Over Volt Prot", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 10.0, "li_base_max": 19.0, "step": 0.1, "mode": "box", "link_b1": "over_voltage_protection"} },
            
    0x28: { "key": "set_over_recover_vol", "name": "Set Over Volt Rec", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "base_min": 9.0, "base_max": 17.0, "li_base_min": 9.0, "li_base_max": 18.0, "step": 0.1, "mode": "box", "link_b1": "over_voltage_recovery"} },
            
    0x29: { "key": "set_light_on_vol", "name": "Set Light ON Volt", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "min": 0.0, "max": 50.0, "step": 1.0, "mode": "box", "link_b1": "light_control_on_voltage"} },
    0x2A: { "key": "set_light_off_vol", "name": "Set Light OFF Volt", "unit": "V", "data_len": 2, "scale": 0.01, "valid_bytes": [5, 6], 
            "ha": {"type": "number", "min": 0.0, "max": 50.0, "step": 1.0, "mode": "box", "link_b1": "light_control_off_voltage"} },
    0x2B: { "key": "set_light_on_delay", "name": "Set Light ON Delay", "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0, "max": 999, "step": 1, "mode": "box", "link_b1": "light_control_on_delay"} },
    0x2C: { "key": "set_light_off_delay", "name": "Set Light OFF Delay", "unit": "s", "data_len": 2, "scale": 1, "valid_bytes": [5, 6], "ha": {"type": "number", "min": 0, "max": 999, "step": 1, "mode": "box", "link_b1": "light_control_off_delay"} },
}

CLOCK_SET = {"year": 2, "month": 3, "day": 4, "hour": 5, "minute": 6}
