import time
import yaml
import signal
import sys
import logging
from core_logging import setup_global_logging
from core_mqtt import RobustMQTTClient 
from core_tcp import RobustTCPClient    # ✅ 確認使用同步 TCP
from ampinvt_proto import AmpinvtProtocol 
from command_handler import CommandHandler
from ha_manager import HAManager
import mppt_register_map as rmap

logger = None
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    try:
        with open("config.yaml", "r") as f: config = yaml.safe_load(f)
        modbus = config.get('modbus', {})
        raw = modbus.get('unit_ids', [1])
        if isinstance(raw, list):
            ids = []
            for x in raw:
                try: ids.append(int(x))
                except: pass
            modbus['unit_ids'] = ids if ids else [1]
        elif isinstance(raw, str):
            modbus['unit_ids'] = [int(x) for x in raw.split(',') if x.strip().isdigit()]
        elif isinstance(raw, int):
            modbus['unit_ids'] = [raw]
        else:
            modbus['unit_ids'] = [1]
        config['modbus'] = modbus
        return config
    except Exception as e:
        print(f"❌ 設定檔讀取失敗: {e}")
        return None

def graceful_exit(signum, frame):
    logger.info("🛑 收到關閉指令...")
    if app_config and ha_mgr and mqtt_client:
        if app_config.get('mqtt', {}).get('reset_discovery_on_exit'):
            try: ha_mgr.clear_all_discovery(app_config['modbus']['unit_ids']); time.sleep(1)
            except: pass
    if mqtt_client:
        mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
    sys.exit(0)

# 🟢 [核心功能] 同步掃描設備資訊
def scan_device_details(protocol, unit_ids):
    """
    啟動時掃描：取得電池串數與類型，用於生成智慧滑桿
    """
    logger.info("🔍 正在偵測設備資訊 (串數/類型)...")
    details = {} 
    
    for uid in unit_ids:
        try:
            # 嘗試讀取 3 次
            for _ in range(3):
                data = protocol.read_b1_data(uid)
                if data:
                    b_type = data[8]  # 電池類型
                    b_count = data[10] # 電池串數
                    
                    if 1 <= b_count <= 16:
                        details[uid] = {"count": b_count, "type": b_type}
                        t_str = "鋰電池" if b_type == 3 else "鉛酸"
                        logger.info(f"✅ 設備 #{uid}: {t_str}, {b_count} 串 ({b_count*12}V)")
                        break
                time.sleep(0.2) # 同步版需要休息一下
        except Exception as e:
            logger.warning(f"⚠️ 設備 #{uid} 掃描失敗: {e}")
            
    return details

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    app_config = load_config()
    if not app_config: sys.exit(1)

    debug_mode = app_config.get('system', {}).get('debug', False)
    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    
    logger.info("🚀 啟動 V5.7.1 智慧電壓範圍限制版 (Sync Core)")
    
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config.get('system', {})
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    # 初始化模組 (同步版)
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)
    cmd_handler = CommandHandler(protocol, ha_mgr, timezone_offset=sys_cfg.get('timezone_offset', 8))

    # 🟢 1. 執行啟動掃描
    device_details = scan_device_details(protocol, modbus_cfg['unit_ids'])

    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    # 2. MQTT 連線與 Discovery
    def on_mqtt_ready():
        # 將掃描到的詳情傳給 HA Manager
        ha_mgr.send_discovery(modbus_cfg['unit_ids'], device_details)
        
        mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
        for t in ["switch", "button", "number", "select"]:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        logger.info("👂 MQTT 準備就緒")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    consecutive_errors = 0    
    MAX_ERRORS = 20
    offline_devices = {} 

    # 🟢 插隊指令處理 (同步版)
    def process_commands():
        count = 0
        while not mqtt_client.msg_queue.empty():
            msg = mqtt_client.msg_queue.get()
            if isinstance(msg, dict): t, p = msg.get('topic'), msg.get('payload')
            else: t, p = getattr(msg, 'topic', None), getattr(msg, 'payload', None)
            
            if not t or p is None: continue
            p_str = p.decode('utf-8').strip() if isinstance(p, bytes) else str(p).strip()

            logger.info(f"⚡ 插隊指令: {t} -> {p_str}")
            cmd_handler.process_message(t, p_str)
            count += 1
        return count

    # 3. 主迴圈
    while True:
        try:
            any_success = False 
            current_time = time.time()

            for uid in modbus_cfg['unit_ids']:
                # 插隊檢查
                if process_commands() > 0:
                    time.sleep(0.2)

                # 輪詢邏輯
                if uid in offline_devices:
                    if current_time < offline_devices[uid]: continue
                    else: logger.info(f"🔄 重試設備 #{uid}")

                try:
                    raw_data = protocol.read_b1_data(uid)
                    if raw_data:
                        vals = protocol.decode(raw_data, rmap.B1_INFO)
                        bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        
                        if uid in offline_devices: del offline_devices[uid]
                        any_success = True
                    
                    time.sleep(app_config['polling']['delay_between_units'])
                    
                except Exception:
                    logger.warning(f"⚠️ 設備 #{uid} 讀取失敗")
                    offline_devices[uid] = current_time + 60
            
            # 看門狗
            if any_success or len(offline_devices) < len(modbus_cfg['unit_ids']):
                consecutive_errors = 0 
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    logger.warning(f"⚠️ 全部連線失敗 ({consecutive_errors}/{MAX_ERRORS})")

            if consecutive_errors >= MAX_ERRORS:
                logger.critical("❌ 系統嚴重故障，強制重啟")
                mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
                sys.exit(1)

        except Exception as e:
            logger.error(f"主迴圈錯誤: {e}")
            consecutive_errors += 1
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
