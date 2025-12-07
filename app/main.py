import time
import yaml
import signal
import sys
import logging
from core_logging import setup_global_logging
from core_mqtt import RobustMQTTClient 
from core_tcp import RobustTCPClient    # 回歸 RobustTCPClient
from ampinvt_proto import AmpinvtProtocol # 回歸 AmpinvtProtocol
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
        raw = modbus.get('unit_ids', "1")
        if isinstance(raw, str):
            modbus['unit_ids'] = [int(x) for x in raw.split(',') if x.strip().isdigit()]
        elif isinstance(raw, int):
            modbus['unit_ids'] = [raw]
        return config
    except: return None

def graceful_exit(signum, frame):
    logger.info("🛑 收到關閉指令...")
    if app_config and ha_mgr and mqtt_client:
        if app_config['mqtt']['reset_discovery_on_exit']:
            try: ha_mgr.clear_all_discovery(app_config['modbus']['unit_ids']); time.sleep(1)
            except: pass
    if mqtt_client:
        mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
    sys.exit(0)

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    app_config = load_config()
    if not app_config: sys.exit(1)

    debug_mode = app_config['system'].get('debug', False)
    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    
    logger.info("🚀 啟動 V5.5 插隊優先版 (Socket Core)")
    
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config['system']
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    # 初始化模組
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)
    
    # 🟢 傳入 ha_mgr 讓 Handler 可以做回讀更新
    cmd_handler = CommandHandler(protocol, ha_mgr, timezone_offset=sys_cfg.get('timezone_offset', 8))

    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    def on_mqtt_ready():
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
        for t in ["switch", "button", "number", "select"]:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        logger.info("👂 MQTT 準備就緒")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    consecutive_errors = 0    
    MAX_ERRORS = 20
    offline_devices = {} # 黑名單機制

    # 🟢 定義處理指令的函式 (同步版)
    def process_commands():
        """處理佇列中所有的 MQTT 指令"""
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

    # 主迴圈
    while True:
        try:
            any_success = False 
            current_time = time.time()

            for uid in modbus_cfg['unit_ids']:
                # 🟢 [關鍵優化] 在讀取每一台之前，先檢查有沒有指令要插隊！
                # 這樣最慢只需要等待「一台」設備的讀取時間 (約 0.2~0.5s)
                if process_commands() > 0:
                    # 如果有處理指令，稍微休息一下讓總線緩衝
                    time.sleep(0.2)

                # --- 正常的輪詢邏輯 ---
                # 黑名單檢查
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
            
            # Watchdog 邏輯
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
