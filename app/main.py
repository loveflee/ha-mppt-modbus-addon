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
            # 安全檢查：確保 index 不會超出範圍 (現在 raw_bytes 是 93 bytes)
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

        # 安全檢查
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
            
            # 應用縮放
            if scale != 1: final_val = round(val / scale, 2)
            else: final_val = val
            result[key] = final_val
        except Exception as e:
            print(f"⚠ 解析錯誤 [{key}]: {e}")
    return result

def load_config(path="config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f: return yaml.safe_load(f)
    except: return {}

def main():
    cfg = load_config()
    unit_ids = cfg['modbus']['unit_ids']
    poll_cfg = cfg['polling']
    
    print("🚀 啟動 MPPT 監控 (數據修復版 - Full Offset)")
    
    mqtt = HomeAssistantMQTT(cfg['mqtt'], unit_ids)
    mqtt.connect()
    
    mb = ModbusClient(cfg['modbus'], debug=True)
    
    while True:
        try:
            # 指令處理
            while not mqtt.command_queue.empty():
                cmd = mqtt.command_queue.get()
                print(f"⚡ 執行指令: {cmd.name} -> {cmd.value}")
                success = False
                if cmd.cmd_type == "C0":
                    success = mb.write_mppt_command(cmd.unit_id, cmd.code)
                elif cmd.cmd_type == "D0":
                    success = mb.write_mppt_setting(cmd.unit_id, cmd.code, cmd.value, cmd.data_len)
                if success: time.sleep(1)

            # 輪詢設備
            for uid in unit_ids:
                # 讀取完整 93 Bytes B1 封包
                raw_b1 = mb.read_mppt_b1_full(uid)
                
                if raw_b1 and len(raw_b1) == 93:
                    # 1. 解析數值
                    data_vals = decode_mppt_data(raw_b1, rmap.B1_INFO)
                    mqtt.publish_states(uid, data_vals, sub_topic="state_b1")
                    
                    # 2. 解析狀態
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
