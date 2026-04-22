import time
import yaml
import signal
import sys
import logging
import importlib
import os
import struct

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

discovered_devices = set()
device_details_cache = {}

def load_config():
    """載入設定，並處理黑名單預設值"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        with open(config_path, "r") as f: config = yaml.safe_load(f)
        if 'system' not in config: config['system'] = {}
        if 'language' not in config['system']: config['system']['language'] = 'tw'
        
        # 🟢 處理黑名單設定
        if 'blacklist' not in config: config['blacklist'] = {}
        config['blacklist']['fail_threshold'] = config['blacklist'].get('fail_threshold', 20)
        config['blacklist']['isolation_time'] = config['blacklist'].get('isolation_time', 60)
        config['blacklist']['long_delay_threshold'] = config['blacklist'].get('long_delay_threshold', 10)
        config['blacklist']['long_delay'] = config['blacklist'].get('long_delay', 3600)
        
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
    """處理程序終止訊號"""
    logger.info("🛑 收到關閉指令...")
    if app_config and ha_mgr and mqtt_client:
        if app_config.get('mqtt', {}).get('reset_discovery_on_exit'):
            try: ha_mgr.clear_all_discovery(list(discovered_devices)); time.sleep(1)
            except: pass
    if mqtt_client:
        logger.info("👋 系統關閉，發送全域離線 LWT")
        mqtt_client.publish(ha_mgr.global_avail_topic, "offline", retain=True)
    sys.exit(0)

def scan_single_device(protocol, uid, rmap):
    """啟動時，掃描單個設備以識別類型，只嘗試 3 次"""
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        try:
            data = protocol.read_b1_data(uid)
            if data:
                b_type = data[8]; b_count = data[10]; hw_max_raw = struct.unpack('>H', data[24:26])[0]
                hw_max_amp = round(hw_max_raw / 100.0, 1)
                if 1 <= b_count <= 16:
                    t_map = rmap.B1_INFO[0].get('map', {})
                    t_str = t_map.get(b_type, str(b_type))
                    logger.info(f"✅ 設備 #{uid} 識別成功: {t_str}, {b_count}S, Max {hw_max_amp}A")
                    return { "count": b_count, "type": b_type, "hw_max": hw_max_amp }
        except Exception: pass
        time.sleep(0.5)
    logger.warning(f"⚠️ 設備 #{uid} 啟動掃描失敗 (無回應)，暫不註冊，等待上線...")
    return None

def main():
    global mqtt_client, ha_mgr, app_config, logger, discovered_devices, device_details_cache
    
    app_config = load_config()
    if not app_config: sys.exit(1)

    sys_cfg = app_config.get('system', {})
    debug_mode = sys_cfg.get('debug', False)
    lang = sys_cfg.get('language', 'tw')
    
    BL_CFG = app_config['blacklist']
    FAIL_THRESHOLD = BL_CFG['fail_threshold']
    INITIAL_DELAY = BL_CFG['isolation_time']
    LONG_DELAY_THRESHOLD = BL_CFG['long_delay_threshold']
    LONG_DELAY = BL_CFG['long_delay']

    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    logger.info(f"🚀 啟動 V7.7 多階段懲罰版 (Language: {lang})")

    try:
        module_name = f"language.{lang}"
        rmap = importlib.import_module(module_name)
        logger.info(f"✅ 成功載入語系: {module_name}")
    except ImportError as e:
        logger.error(f"❌ 找不到語系 {module_name} ({e})，使用 tw")
        import language.tw as rmap

    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg, rmap)
    cmd_handler = CommandHandler(protocol, ha_mgr, rmap, timezone_offset=sys_cfg.get('timezone_offset', 8))

    initial_online_ids = []
    logger.info("🔍 執行啟動掃描...")
    for uid in modbus_cfg['unit_ids']:
        details = scan_single_device(protocol, uid, rmap)
        if details:
            device_details_cache[uid] = details
            initial_online_ids.append(uid)
            discovered_devices.add(uid)

    logger.info(f"👻 設定全域 LWT: {ha_mgr.global_avail_topic}")
    mqtt_client.set_lwt(ha_mgr.global_avail_topic, payload="offline", retain=True)

    def on_mqtt_ready():
        if initial_online_ids:
            ha_mgr.send_discovery(initial_online_ids, device_details_cache)
            for uid in initial_online_ids:
                ha_mgr.publish_connectivity_state(uid, True)
        
        mqtt_client.publish(ha_mgr.global_avail_topic, "online", retain=True)
        # 👇 修正：補上 "text" 網域訂閱
        for t in ["switch", "button", "number", "select", "text"]:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        logger.info("👂 MQTT 準備就緒")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    consecutive_errors = 0    
    MAX_ERRORS = 20
    
    current_ts = time.time()
    offline_devices = {}
    device_fail_counts = {}

    for uid in modbus_cfg['unit_ids']:
        device_fail_counts[uid] = 0
        if uid not in discovered_devices:
            offline_devices[uid] = current_ts 

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

            process_commands()

            for uid in modbus_cfg['unit_ids']:
                
                if uid in offline_devices:
                    if current_time < offline_devices[uid]: continue 
                    else: logger.info(f"🔄 嘗試聯繫設備 #{uid} ...")

                if process_commands() > 0: time.sleep(0.2)

                try:
                    raw_data = protocol.read_b1_data(uid)
                    if raw_data:
                        if uid not in discovered_devices:
                            logger.info(f"🎉 發現新上線設備 #{uid}！")
                            b_type = raw_data[8]; b_count = raw_data[10]; hw_max = round(struct.unpack('>H', raw_data[24:26])[0] / 100.0, 1)
                            if 1 <= b_count <= 16:
                                details = {"count": b_count, "type": b_type, "hw_max": hw_max}
                                device_details_cache[uid] = details
                                ha_mgr.send_discovery([uid], device_details_cache)
                                discovered_devices.add(uid)
                                ha_mgr.publish_connectivity_state(uid, True)
                            else: raise Exception("Invalid Data")

                        vals = protocol.decode(raw_data, rmap.B1_INFO)
                        bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        
                        if device_fail_counts.get(uid, 0) > 0:
                            logger.info(f"✅ 設備 #{uid} 連線恢復")
                            device_fail_counts[uid] = 0
                            ha_mgr.publish_device_availability(uid, "online")
                            ha_mgr.publish_connectivity_state(uid, True)

                        if uid in offline_devices: del offline_devices[uid]
                        any_success = True
                    else:
                        raise Exception("Empty Data") 
                    time.sleep(app_config['polling']['delay_between_units'])

                except Exception:
                    fail_count = device_fail_counts.get(uid, 0) + 1
                    device_fail_counts[uid] = fail_count
                    
                    delay = INITIAL_DELAY
                    
                    if fail_count >= LONG_DELAY_THRESHOLD:
                        if fail_count == LONG_DELAY_THRESHOLD:
                             logger.error(f"❌ 設備 #{uid} 連續失敗達 {LONG_DELAY_THRESHOLD} 次！進入【懲罰性隔離】{LONG_DELAY} 秒。")
                        delay = LONG_DELAY
                    
                    if fail_count == FAIL_THRESHOLD:
                        logger.error(f"❌ 設備 #{uid} 連續失敗 {FAIL_THRESHOLD} 次，標記為【離線】")
                        ha_mgr.publish_device_availability(uid, "offline")
                        ha_mgr.publish_connectivity_state(uid, False)
                    
                    offline_devices[uid] = current_time + delay
            
            if any_success or len(offline_devices) < len(modbus_cfg['unit_ids']):
                consecutive_errors = 0 
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    logger.warning(f"⚠️ 所有設備皆無回應 ({consecutive_errors}/{MAX_ERRORS})")

            if consecutive_errors >= MAX_ERRORS:
                logger.critical("❌ 系統嚴重通訊故障，強制重啟")
                mqtt_client.publish(ha_mgr.global_avail_topic, "offline", retain=True)
                sys.exit(1)

        except Exception as e:
            logger.error(f"主迴圈發生意外錯誤: {e}")
            consecutive_errors += 1
            time.sleep(1)
            
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
