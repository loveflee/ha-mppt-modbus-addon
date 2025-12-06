import time
import yaml
import signal
import sys
import logging # 引入標準庫
from datetime import datetime, timedelta, timezone

# 🟢 [修改] 引入我們剛寫好的日誌模組
from core_logging import setup_global_logging

import mppt_register_map as rmap
from core_tcp import RobustTCPClient
from core_mqtt import RobustMQTTClient
from ampinvt_proto import AmpinvtProtocol
from ha_manager import HAManager
from command_handler import CommandHandler

# 全域變數
mqtt_client = None
ha_mgr = None
app_config = None
logger = None # 這是 Main 專用的 logger

def load_config():
    """讀取設定檔"""
    default_config = {
        "system": {"debug": False, "timezone_offset": 8},
        "modbus": {"host": "127.0.0.1", "port": 502, "timeout": 3.0, "unit_ids": [1]},
        "mqtt": {"broker": "localhost", "port": 1883, "username": "", "password": "", 
                 "discovery_prefix": "homeassistant", "node_id": "mppt", "device_name": "MPPT", 
                 "reset_discovery_on_exit": False},
        "polling": {"poll_interval": 3, "delay_between_units": 0.5}
    }
    try:
        with open("config.yaml", "r") as f: 
            user_config = yaml.safe_load(f) or {}
    except: user_config = {}

    config = default_config.copy()
    for section, params in user_config.items():
        if section in config and isinstance(params, dict):
            config[section].update(params)

    modbus = config['modbus']
    raw_ids = modbus.get('unit_ids', [1])
    if isinstance(raw_ids, str):
        modbus['unit_ids'] = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
    elif isinstance(raw_ids, int):
        modbus['unit_ids'] = [raw_ids]
        
    return config

def graceful_exit(signum, frame):
    logger.info(f"🛑 收到關閉指令 ({signum})，正在清理資源...")
    if app_config and ha_mgr and mqtt_client:
        if app_config['mqtt']['reset_discovery_on_exit']:
            logger.warning("🧹 清除 HA 實體...")
            try: ha_mgr.clear_all_discovery(app_config['modbus']['unit_ids']); time.sleep(1)
            except: pass
    if mqtt_client:
        logger.info("🔌 斷開 MQTT 連線...")
        mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
    sys.exit(0)

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    # 1. 載入設定
    app_config = load_config()
    if not app_config: sys.exit(1)

    # 2. 🟢 初始化日誌系統 (只需做一次，其他模組就會自動生效)
    debug_mode = app_config['system'].get('debug', False)
    # 設定好全域日誌，並取得 Main 專用的 logger
    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    
    logger.info("🚀 MPPT 監控系統啟動 (V5.3 日誌模組化版)")
    
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config['system']
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    # 3. 初始化模組
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)
    
    # 傳入 Handler
    cmd_handler = CommandHandler(protocol, timezone_offset=sys_cfg.get('timezone_offset', 8))

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

    # 4. 主迴圈
    while True:
        # A. 指令處理
        try:
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                if isinstance(msg, dict): t, p = msg.get('topic'), msg.get('payload')
                else: t, p = getattr(msg, 'topic', None), getattr(msg, 'payload', None)
                
                if not t or p is None: continue
                p_str = p.decode('utf-8').strip() if isinstance(p, bytes) else str(p).strip()

                logger.info(f"📩 指令 [{t}]: {p_str}")
                cmd_handler.process_message(t, p_str)

        except Exception as e:
            logger.error(f"MQTT 迴圈錯誤: {e}")

        # B. 輪詢數據
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
            
            if any_success:
                consecutive_errors = 0 
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    logger.warning(f"⚠️ 連續讀取失敗 ({consecutive_errors}/{MAX_ERRORS})")

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
