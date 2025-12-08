import time
import yaml
import signal
import sys
import logging
import importlib # 🟢 新增
from core_logging import setup_global_logging
from core_mqtt import RobustMQTTClient 
from core_tcp import RobustTCPClient
from ampinvt_proto import AmpinvtProtocol 
from command_handler import CommandHandler
from ha_manager import HAManager

logger = None
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    try:
        with open("config.yaml", "r") as f: config = yaml.safe_load(f)
        
        # 🟢 讀取語系設定，預設 tw
        if 'system' not in config: config['system'] = {}
        if 'language' not in config['system']: config['system']['language'] = 'tw'

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

# 🟢 修改：需要傳入 rmap 物件
def scan_device_details(protocol, unit_ids, rmap):
    logger.info("🔍 正在偵測設備資訊 (串數/類型)...")
    details = {} 
    for uid in unit_ids:
        try:
            for _ in range(3):
                data = protocol.read_b1_data(uid)
                if data:
                    b_type = data[8]
                    b_count = data[10]
                    if 1 <= b_count <= 16:
                        details[uid] = {"count": b_count, "type": b_type}
                        # 🟢 從 rmap 取得對應的文字
                        t_map = rmap.B1_INFO[0]['map'] # 電池類型是第0個
                        t_str = t_map.get(b_type, f"Type {b_type}")
                        logger.info(f"✅ 設備 #{uid}: {t_str}, {b_count} 串 ({b_count*12}V)")
                        break
                time.sleep(0.2)
        except Exception as e:
            logger.warning(f"⚠️ 設備 #{uid} 掃描失敗: {e}")
    return details

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    app_config = load_config()
    if not app_config: sys.exit(1)

    sys_cfg = app_config.get('system', {})
    debug_mode = sys_cfg.get('debug', False)
    lang = sys_cfg.get('language', 'tw') # 🟢 取得語系

    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    
    logger.info(f"🚀 啟動 V7.0 多語系版 (Language: {lang})")

    # 🟢 動態載入地圖模組
    try:
        module_name = f"mppt_map_{lang}"
        rmap = importlib.import_module(module_name)
        logger.info(f"✅ 成功載入地圖檔: {module_name}.py")
    except ImportError:
        logger.error(f"❌ 找不到語系檔 {module_name}.py，回退使用 tw")
        import mppt_map_tw as rmap

    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    
    # 🟢 注入 rmap
    ha_mgr = HAManager(mqtt_client, mqtt_cfg, rmap)
    cmd_handler = CommandHandler(protocol, ha_mgr, rmap, timezone_offset=sys_cfg.get('timezone_offset', 8))

    device_details = scan_device_details(protocol, modbus_cfg['unit_ids'], rmap)

    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    def on_mqtt_ready():
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

    while True:
        try:
            any_success = False 
            current_time = time.time()

            for uid in modbus_cfg['unit_ids']:
                if process_commands() > 0: time.sleep(0.2)

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
