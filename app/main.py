import time
import yaml
import sys
import struct
from typing import Dict, Any, List
import mppt_register_map as rmap
from modbus_client import ModbusClient
from mqtt_client import HomeAssistantMQTT

def decode_mppt_data(raw_bytes: bytes, map_list: List[Dict], is_bits_map: bool = False) -> Dict[str, Any]:
    result = {}
    if is_bits_map:
        for key, info in map_list.items():
            byte_idx = info['byte']
            bit_idx = info['bit']
            if byte_idx < len(raw_bytes):
                is_on = bool((raw_bytes[byte_idx] >> bit_idx) & 0x01)
                result[key] = "ON" if is_on else "OFF"
        return result

    for item in map_list:
        key = item['key']
        offset = item['offset']
        length = item['length']
        scale = item['scale']
        is_signed = item['signed']

        if offset + length > len(raw_bytes): continue
        chunk = raw_bytes[offset : offset + length]
        val = 0
        try:
            if length == 1: val = chunk[0]
            elif length == 2:
                fmt = '>h' if is_signed else '>H'
                val = struct.unpack(fmt, chunk)[0]
            elif length == 4:
                fmt = '>i' if is_signed else '>I'
                val = struct.unpack(fmt, chunk)[0]
            
            if scale != 1: final_val = round(val / scale, 2)
            else: final_val = val
            result[key] = final_val
        except Exception as e:
            # 只有在除錯模式下才印出解析錯誤，保持日誌乾淨
            pass 
    return result

def load_config(path="config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f: return yaml.safe_load(f)
    except: return {}

def main():
    cfg = load_config()
    unit_ids = cfg.get('modbus', {}).get('unit_ids', [1])
    poll_cfg = cfg.get('polling', {'poll_interval': 3, 'delay_between_units': 0.5})
    
    # ✅ 關鍵修復：正確讀取設定檔中的 debug 選項
    system_cfg = cfg.get('system', {})
    debug_mode = system_cfg.get('debug', False)
    
    print("==============================================")
    print(f"🚀 啟動 MPPT 監控 (V1.7.1 Debug修復版)")
    print(f"🎯 設備列表: {unit_ids}")
    print(f"🛠  除錯模式: {'開啟 (會顯示 TX/RX)' if debug_mode else '關閉 (僅顯示關鍵訊息)'}")
    print("==============================================\n")
    
    mqtt = HomeAssistantMQTT(cfg['mqtt'], unit_ids)
    mqtt.connect()
    
    # ✅ 將讀取到的 debug_mode 傳入，而不是寫死 True
    mb = ModbusClient(cfg['modbus'], debug=debug_mode)
    
    while True:
        try:
            while not mqtt.command_queue.empty():
                cmd = mqtt.command_queue.get()
                print(f"⚡ 執行指令: {cmd.name} -> {cmd.value}")
                success = False
                if cmd.cmd_type == "C0": success = mb.write_mppt_command(cmd.unit_id, cmd.code)
                elif cmd.cmd_type == "D0": success = mb.write_mppt_setting(cmd.unit_id, cmd.code, cmd.value, cmd.data_len)
                if success: time.sleep(1)

            for uid in unit_ids:
                raw_b1 = mb.read_mppt_b1_full(uid)
                if raw_b1 and len(raw_b1) == 93:
                    data_vals = decode_mppt_data(raw_b1, rmap.B1_INFO)
                    mqtt.publish_states(uid, data_vals, sub_topic="state_b1")
                    data_bits = decode_mppt_data(raw_b1, rmap.B1_STATUS_BITS, is_bits_map=True)
                    mqtt.publish_states(uid, data_bits, sub_topic="state_bits")
                time.sleep(poll_cfg['delay_between_units'])

            time.sleep(poll_cfg['poll_interval'])

        except KeyboardInterrupt:
            mb.close()
            break
        except Exception as e:
            print(f"❌ 主迴圈錯誤: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
