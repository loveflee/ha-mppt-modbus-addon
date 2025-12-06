import time
import yaml
import signal
import sys
from core_tcp import RobustTCPClient
from core_mqtt import RobustMQTTClient
from ampinvt_proto import AmpinvtProtocol
from ha_manager import HAManager
import mppt_register_map as rmap

# 🟢 [NEW] 引入新的指令處理器
from command_handler import CommandHandler

# 全域變數
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    try:
        with open("config.yaml", "r") as f: 
            config = yaml.safe_load(f)
        # 自動防呆：轉 unit_ids 為列表
        modbus = config.get('modbus', {})
        raw = modbus.get('unit_ids', "1")
        if isinstance(raw, str):
            modbus['unit_ids'] = [int(x) for x in raw.split(',') if x.strip().isdigit()]
        elif isinstance(raw, int):
            modbus['unit_ids'] = [raw]
        return config
    except Exception as e:
        print(f"❌ 設定檔讀取失敗: {e}")
        return None

def graceful_exit(signum, frame):
    print(f"\n🛑 收到終止訊號，準備關閉...")
    if app_config and ha_mgr and app_config.get('mqtt', {}).get('reset_discovery_on_exit'):
        try:
            ha_mgr.clear_all_discovery(app_config['modbus']['unit_ids'])
            time.sleep(1)
        except: pass
    if mqtt_client: mqtt_client.client.disconnect()
    sys.exit(0)

def main():
    global mqtt_client, ha_mgr, app_config
    
    # 1. 初始化設定
    app_config = load_config()
    if not app_config: sys.exit(1)

    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config.get('system', {})
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    
    print(f"🚀 MPPT 監控系統 V5.0 (架構升級版) 啟動")

    # 2. 建立連線元件
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    protocol = AmpinvtProtocol(tcp, debug=sys_cfg.get('debug', False))
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)
    
    # 🟢 [NEW] 建立指令處理器 (注入 protocol 與 時區設定)
    cmd_handler = CommandHandler(protocol, timezone_offset=sys_cfg.get('timezone_offset', 8))

    def on_mqtt_ready():
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        # 訂閱所有控制指令
        for t in ["switch", "button", "number", "select"]:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        print(f"👂 監聽指令中...")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    # 看門狗變數
    consecutive_errors = 0    
    MAX_ERRORS = 20

    # 3. 主迴圈 (現在變得非常乾淨！)
    while True:
        # --- 任務 A: 處理指令 (交給 Handler) ---
        try:
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                
                # 資料清理
                if isinstance(msg, dict):
                    topic = msg.get('topic'); payload_raw = msg.get('payload')
                else:
                    topic = getattr(msg, 'topic', None); payload_raw = getattr(msg, 'payload', None)

                if not topic or payload_raw is None: continue

                # Payload 轉字串
                if isinstance(payload_raw, bytes): payload = payload_raw.decode('utf-8').strip()
                else: payload = str(payload_raw).strip()

                print(f"📩 收到指令 [{topic}]: {payload}")
                
                # 🟢 [关键] 一行程式碼搞定所有邏輯！
                cmd_handler.process_message(topic, payload)

        except Exception as e:
            print(f"⚠️ 指令處理迴圈異常: {e}")

        # --- 任務 B: 輪詢數據 (保持原樣) ---
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
                except: pass
            
            # 看門狗邏輯
            if any_success: consecutive_errors = 0
            else: consecutive_errors += 1
            
            if consecutive_errors >= MAX_ERRORS:
                print("❌ [Watchdog] 系統嚴重故障，強制重啟")
                sys.exit(1)

        except Exception as e:
            print(f"⚠️ 主迴圈異常: {e}")
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
