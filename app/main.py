import time
import yaml
import signal
import sys
import mppt_register_map as rmap
from core_tcp import RobustTCPClient
from core_mqtt import RobustMQTTClient
from ampinvt_proto import AmpinvtProtocol
from ha_manager import HAManager

# 全域變數以便 Signal Handler 存取
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    try:
        with open("config.yaml", "r") as f: return yaml.safe_load(f)
    except: return {}

def graceful_exit(signum, frame):
    """處理程式關閉訊號"""
    print(f"\n🛑 收到終止訊號 ({signum})，準備關閉...")
    
    if app_config and ha_mgr and mqtt_client:
        reset_on_exit = app_config.get('mqtt', {}).get('reset_discovery_on_exit', False)
        
        if reset_on_exit:
            print("⚠️ 偵測到 reset_discovery_on_exit = True")
            try:
                unit_ids = app_config['modbus']['unit_ids']
                ha_mgr.clear_all_discovery(unit_ids)
                time.sleep(2)
            except Exception as e:
                print(f"❌ 清除過程發生錯誤: {e}")
    
    if mqtt_client:
        print("🔌 斷開 MQTT 連線...")
        
    print("👋 Bye!")
    sys.exit(0)

def main():
    global mqtt_client, ha_mgr, app_config
    
    app_config = load_config()
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    
    # 註冊訊號監聽
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    
    print("🚀 啟動 MPPT 監控 (V2.0)")

    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    protocol = AmpinvtProtocol(tcp, debug=app_config['system']['debug'])
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)

    def on_mqtt_ready():
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        # 訂閱所有控制指令
        topics = ["switch", "button", "number", "select"]
        for t in topics:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        print(f"👂 已訂閱控制指令")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    while True:
        try:
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                if isinstance(msg, dict):
                    topic = msg.get('topic'); payload_raw = msg.get('payload')
                else:
                    topic = getattr(msg, 'topic', None); payload_raw = getattr(msg, 'payload', None)

                if not topic or payload_raw is None: continue

                # Payload 轉字串
                if isinstance(payload_raw, bytes): payload = payload_raw.decode('utf-8').strip()
                else: payload = str(payload_raw).strip()

                print(f"📩 收到指令 [{topic}]: {payload}")
                
                try:
                    parts = topic.split('/') # .../domain/entity_base/key/set
                    key = parts[-2]
                    entity_base = parts[-3]
                    domain = parts[-4]
                    uid = int(entity_base.split('_')[-1])

                    # 👉 處理 Switch
                    if domain == "switch":
                        switch_def = rmap.CONTROL_SWITCHES.get(key)
                        if switch_def:
                            cmd = switch_def['on_code'] if payload.upper()=="ON" else switch_def['off_code']
                            protocol.write_c0_command(uid, cmd)

                    # 👉 處理 Button
                    elif domain == "button":
                        btn_def = rmap.CONTROL_BUTTONS.get(key)
                        if btn_def: protocol.write_c0_command(uid, btn_def['code'])

                    # 👉 處理 Number
                    elif domain == "number":
                        target_item = None
                        target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key:
                                target_item = item; target_code = code; break
                        
                        if target_item:
                            val = float(payload)
                            print(f"👉 設定參數 [{key}] = {val}")
                            protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])

                    # 👉 🟢 處理 Select (下拉選單 - 增強版)
                    elif domain == "select":
                        target_item = None
                        target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key:
                                target_item = item; target_code = code; break
                        
                        if target_item:
                            map_dict = None
                            for b1_item in rmap.B1_INFO:
                                if b1_item['key'] == target_item['ha']['link_b1']:
                                    map_dict = b1_item.get('map')
                                    break
                            
                            if map_dict:
                                int_val = None
                                # 策略 1: 嘗試完全匹配 (Value -> Key)
                                for k, v in map_dict.items():
                                    if v == payload: 
                                        int_val = k
                                        break
                                
                                # 策略 2: 嘗試前綴 ID 解析 (例如 "3:鋰電池" -> 3)
                                if int_val is None and ":" in payload:
                                    try:
                                        prefix = payload.split(':')[0]
                                        if prefix.isdigit():
                                            potential_id = int(prefix)
                                            # 確認這個 ID 是否真的在 map 中
                                            if potential_id in map_dict:
                                                int_val = potential_id
                                                print(f"ℹ️ 使用 ID 匹配: {payload} -> {int_val}")
                                    except: pass

                                if int_val is not None:
                                    print(f"👉 設定模式 [{key}] = {payload} (Val={int_val})")
                                    protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                                else:
                                    print(f"⚠️ 無法找到選項對應數值: {repr(payload)}")
                                    print(f"   系統內的選項 Map: {map_dict}")

                except Exception as e:
                    print(f"⚠️ 指令執行錯誤: {e}")

        except Exception as e:
            print(f"⚠️ MQTT Loop 錯誤: {e}")

        # 輪詢數據
        try:
            for uid in modbus_cfg['unit_ids']:
                raw_data = protocol.read_b1_data(uid)
                if raw_data:
                    vals = protocol.decode(raw_data, rmap.B1_INFO)
                    bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                    ha_mgr.publish_state(uid, vals, "state_b1")
                    ha_mgr.publish_state(uid, bits, "state_bits")
                time.sleep(app_config['polling']['delay_between_units'])
        except Exception as e:
            pass
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
