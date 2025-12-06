import time
import yaml
import signal
import sys
import logging
from datetime import datetime, timedelta, timezone

# 匯入模組
import mppt_register_map as rmap
from core_tcp import RobustTCPClient
from core_mqtt import RobustMQTTClient
from ampinvt_proto import AmpinvtProtocol
from ha_manager import HAManager

# --- 全域變數 ---
mqtt_client = None
ha_mgr = None
app_config = None
logger = None

# 🟢 [新增] 設定日誌系統的函式
def setup_logging(debug_mode: bool):
    """
    設定日誌格式與等級
    """
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    level = logging.DEBUG if debug_mode else logging.INFO
    
    # 設定根日誌 (Root Logger)
    logging.basicConfig(level=level, format=log_format, datefmt='%H:%M:%S')
    
    return logging.getLogger("MPPT")

def load_config():
    """
    📖 讀取設定檔 (增強驗證版)
    """
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
    except FileNotFoundError:
        print("⚠️ 找不到 config.yaml，將使用預設值。")
        user_config = {}
    except Exception as e:
        print(f"❌ 設定檔格式錯誤: {e}")
        return None

    # 🟢 [新增] 遞迴合併預設值 (確保所有欄位都有值)
    config = default_config.copy()
    for section, params in user_config.items():
        if section in config and isinstance(params, dict):
            config[section].update(params)

    # --- 防呆處理 ---
    modbus = config['modbus']
    raw_ids = modbus.get('unit_ids', [1])
    
    # 確保 unit_ids 永遠是 List[int]
    if isinstance(raw_ids, str):
        modbus['unit_ids'] = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
    elif isinstance(raw_ids, int):
        modbus['unit_ids'] = [raw_ids]
    elif isinstance(raw_ids, list):
        modbus['unit_ids'] = [int(x) for x in raw_ids if str(x).isdigit()]
        
    return config

def graceful_exit(signum, frame):
    """👋 優雅退場機制"""
    logger.info(f"🛑 收到關閉指令 ({signum})，正在清理資源...")
    
    if app_config and ha_mgr and mqtt_client:
        reset_on_exit = app_config.get('mqtt', {}).get('reset_discovery_on_exit', False)
        if reset_on_exit:
            logger.warning("🧹 正在清除 HA 實體註冊...")
            try:
                unit_ids = app_config['modbus']['unit_ids']
                ha_mgr.clear_all_discovery(unit_ids)
                time.sleep(1)
            except Exception as e:
                logger.error(f"❌ 清除失敗: {e}")
    
    if mqtt_client:
        logger.info("🔌 斷開 MQTT 連線...")
        # 主動發送離線狀態
        if ha_mgr:
            mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
        
    logger.info("👋 Bye!")
    sys.exit(0)

def get_local_time(offset_hours):
    """🌍 計算當地時間"""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=offset_hours)

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    # 1. 載入設定
    app_config = load_config()
    if not app_config: sys.exit(1)

    # 2. 初始化日誌
    debug_mode = app_config['system'].get('debug', False)
    logger = setup_logging(debug_mode)
    
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config['system']
    tz_offset = sys_cfg.get('timezone_offset', 8)
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    
    logger.info(f"🚀 MPPT 監控系統啟動 (V5.2 日誌增強版)")
    logger.info(f"🌍 時區設定: UTC+{tz_offset}")
    logger.debug(f"🔧 設定參數: {app_config}")

    # 3. 初始化模組
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    # 將 logger 傳入 protocol (如果 protocol 支援的話，或者 protocol 內用 print)
    # 這裡我們維持 protocol 原樣，但透過 debug 參數控制它的 print
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)

    # 🟢 [新增] 設定 MQTT LWT
    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    def on_mqtt_ready():
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        # 報平安
        mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
        
        topics = ["switch", "button", "number", "select"]
        for t in topics:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        logger.info("👂 MQTT 連線成功，開始監聽指令")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    consecutive_errors = 0    
    MAX_ERRORS = 20

    # 5. 主迴圈
    while True:
        # --- A. 處理指令 ---
        try:
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                
                # 資料提取與轉型
                if isinstance(msg, dict):
                    topic = msg.get('topic'); payload_raw = msg.get('payload')
                else:
                    topic = getattr(msg, 'topic', None); payload_raw = getattr(msg, 'payload', None)

                if not topic or payload_raw is None: continue

                if isinstance(payload_raw, bytes): payload = payload_raw.decode('utf-8').strip()
                else: payload = str(payload_raw).strip()

                logger.info(f"📩 指令 [{topic}]: {payload}")
                
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
                                logger.info(f"⏰ 同步時間至: {local_dt}")
                                protocol.write_time_sync(uid, local_dt)
                            else:
                                protocol.write_c0_command(uid, btn_def['code'])

                    # Number
                    elif domain == "number":
                        target_item = None; target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key: target_item = item; target_code = code; break
                        if target_item:
                            val = float(payload)
                            logger.info(f"👉 設定參數 [{key}] = {val}")
                            protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])

                    # Select
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
                            
                            int_val = None
                            if map_dict:
                                for k, v in map_dict.items():
                                    if v == payload: int_val = k; break
                                if int_val is None and ":" in payload:
                                    try:
                                        potential_id = int(payload.split(':')[0])
                                        if potential_id in map_dict: int_val = potential_id
                                    except: pass

                            if int_val is not None:
                                logger.info(f"👉 設定模式 [{key}] = {payload} (ID={int_val})")
                                protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                            else:
                                logger.warning(f"⚠️ 找不到選項 '{payload}' 對應的數值")

                except Exception as e:
                    logger.error(f"⚠️ 指令處理失敗: {e}")

        except Exception as e:
            logger.error(f"⚠️ MQTT 迴圈錯誤: {e}")

        # --- B. 輪詢數據 ---
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
                except Exception:
                    pass # 單次讀取失敗不紀錄，交給 Watchdog 統計
            
            if any_success:
                consecutive_errors = 0 
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    logger.warning(f"⚠️ [Watchdog] 連續讀取失敗 ({consecutive_errors}/{MAX_ERRORS})")

            if consecutive_errors >= MAX_ERRORS:
                logger.critical("❌ [Watchdog] 系統嚴重故障，強制重啟")
                mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
                sys.exit(1)

        except Exception as e:
            logger.error(f"⚠️ Main Loop 錯誤: {e}")
            consecutive_errors += 1
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
