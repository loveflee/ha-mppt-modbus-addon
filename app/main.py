import time
import yaml
import signal
import sys
from datetime import datetime, timedelta, timezone 

import mppt_register_map as rmap        
from core_tcp import RobustTCPClient    
from core_mqtt import RobustMQTTClient 
from ampinvt_proto import AmpinvtProtocol 
from ha_manager import HAManager        

# --- 全域變數 ---
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    """讀取設定檔的貼心小幫手"""
    try:
        with open("config.yaml", "r") as f: 
            config = yaml.safe_load(f)
        
        modbus_section = config.get('modbus', {})
        raw_ids = modbus_section.get('unit_ids', "1")
        
        if isinstance(raw_ids, str):
            id_list = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
            config['modbus']['unit_ids'] = id_list
        elif isinstance(raw_ids, int):
            config['modbus']['unit_ids'] = [raw_ids]
        elif isinstance(raw_ids, list):
            config['modbus']['unit_ids'] = [int(x) for x in raw_ids]
            
        return config
    except Exception as e:
        print(f"❌ 哎呀！設定檔讀取失敗: {e}")
        return None

def graceful_exit(signum, frame):
    """👋 優雅退場機制：發送 Offline 訊號"""
    print(f"\n🛑 收到關閉指令 ({signum})，正在收拾行李...")
    
    if app_config and ha_mgr and mqtt_client:
        # 🟢 [NEW] 主動發送下線通知 (Offline)
        print("💤 發送離線狀態 (Offline)...")
        mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)

        reset_on_exit = app_config.get('mqtt', {}).get('reset_discovery_on_exit', False)
        if reset_on_exit:
            print("🧹 正在清除 Home Assistant 上的裝置註冊...")
            try:
                unit_ids = app_config['modbus']['unit_ids']
                ha_mgr.clear_all_discovery(unit_ids)
                time.sleep(2) 
            except Exception as e:
                print(f"❌ 清除失敗: {e}")
    
    if mqtt_client:
        print("🔌 斷開 MQTT 連線...")
        # mqtt_client.client.disconnect() # 選擇性呼叫
        
    print("👋 程式結束，Bye Bye!")
    sys.exit(0)

def get_local_time(offset_hours):
    """🌍 計算正確的當地時間"""
    utc_now = datetime.now(timezone.utc)
    local_dt = utc_now + timedelta(hours=offset_hours)
    return local_dt

def main():
    global mqtt_client, ha_mgr, app_config
    
    app_config = load_config()
    if not app_config:
        sys.exit(1) 

    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config.get('system', {}) 
    
    tz_offset = sys_cfg.get('timezone_offset', 8)
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    
    print(f"🚀 MPPT 監控系統啟動中 (V5.0 - LWT 支援版)")

    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    protocol = AmpinvtProtocol(tcp, debug=sys_cfg.get('debug', False))
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)

    # 🟢 [NEW] 1. 設定遺囑 (LWT) - 必須在 connect() 之前！
    # 這樣如果不幸當機、斷電，Broker 會自動幫我們發送 "offline"
    print(f"👻 設定遺囑 Topic: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    def on_mqtt_ready():
        # A. 遞名片
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        
        # 🟢 [NEW] 2. 報平安：告訴 HA 我們上線了 (Online)
        print("👋 發送上線狀態 (Online)...")
        mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
        
        # B. 豎起耳朵
        topics = ["switch", "button", "number", "select"]
        for t in topics:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        print(f"👂 已就位，隨時準備接收 HA 指令")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect() 

    consecutive_errors = 0    
    MAX_ERRORS = 20

    while True:
        # ==========================
        # 任務 A: 處理 MQTT 指令
        # ==========================
        try:
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                
                if isinstance(msg, dict):
                    topic = msg.get('topic'); payload_raw = msg.get('payload')
                else:
                    topic = getattr(msg, 'topic', None); payload_raw = getattr(msg, 'payload', None)

                if not topic or payload_raw is None: continue

                if isinstance(payload_raw, bytes): payload = payload_raw.decode('utf-8').strip()
                else: payload = str(payload_raw).strip()

                print(f"📩 收到指令 [{topic}]: {payload}")
                
                try:
                    parts = topic.split('/') 
                    key = parts[-2]; entity_base = parts[-3]; domain = parts[-4]
                    uid = int(entity_base.split('_')[-1]) 

                    # Switch
                    if domain == "switch":
                        switch_def = rmap.CONTROL_SWITCHES.get(key)
                        if switch_def:
                            cmd = switch_def['on_code'] if payload.upper()=="ON" else switch_def['off_code']
                            protocol.write_c0_command(uid, cmd)

                    # Button
                    elif domain == "button":
                        btn_def = rmap.CONTROL_BUTTONS.get(key)
                        if btn_def: 
                            if btn_def.get('code') == 0xDF:
                                local_dt = get_local_time(tz_offset)
                                print(f"⏰ 執行時間同步: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                protocol.write_time_sync(uid, local_dt)
                            else:
                                protocol.write_c0_command(uid, btn_def['code'])

                    # Number (D0)
                    elif domain == "number":
                        target_item = None; target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key: target_item = item; target_code = code; break
                        if target_item:
                            val = float(payload)
                            print(f"👉 設定參數 [{key}] = {val}")
                            protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])

                    # Select (D0)
                    elif domain == "select":
                        target_item = None; target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key: target_item = item; target_code = code; break
                        
                        if target_item:
                            map_dict = None
                            for b1_item in rmap.B1_INFO:
                                if b1_item.get('key') == target_item.get('ha', {}).get('link_b1'):
                                    map_dict = b1_item.get('map')
                                    break
                            
                            if map_dict:
                                int_val = None
                                for k, v in map_dict.items():
                                    if v == payload: int_val = k; break
                                if int_val is None and ":" in payload:
                                    try:
                                        potential_id = int(payload.split(':')[0])
                                        if potential_id in map_dict: int_val = potential_id
                                    except: pass

                                if int_val is not None:
                                    print(f"👉 設定模式 [{key}] = {payload} (數值={int_val})")
                                    protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                                else:
                                    print(f"⚠️ 找不到選項數值: {payload}")

                except Exception as e:
                    print(f"⚠️ 指令解析失敗: {e}")

        except Exception as e:
            print(f"⚠️ MQTT 迴圈錯誤: {e}")

        # ==========================
        # 任務 B: 輪詢數據
        # ==========================
        try:
            any_success = False 

            for uid in modbus_cfg['unit_ids']:
                try:
                    raw_data = protocol.read_b1_data(uid)
                    
                    if raw_data:
                        vals = protocol.decode(raw_data, rmap.B1_INFO)
                        bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        any_success = True 
                        
                    time.sleep(app_config['polling']['delay_between_units'])
                    
                except Exception as e_inner:
                    pass 
            
            if any_success:
                consecutive_errors = 0 
                # 🟢 [選用] 成功輪詢時，再次確保狀態為 Online (防止 Broker 重啟後狀態遺失)
                # mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    print(f"⚠️ [Watchdog] 連續讀取失敗 ({consecutive_errors}/{MAX_ERRORS})")

            if consecutive_errors >= MAX_ERRORS:
                print("❌ [Watchdog] 系統嚴重故障，強制重啟")
                # 🟢 [NEW] 既然要死了，也發送離線通知
                mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
                sys.exit(1)

        except Exception as e:
            print(f"⚠️ Main Loop 錯誤: {e}")
            consecutive_errors += 1
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
