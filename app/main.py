import time
import yaml
import signal
import sys
import logging
from core_logging import setup_global_logging
from core_mqtt import RobustMQTTClient 
from core_tcp import RobustTCPClient    # 使用穩定的 Socket 底層
from ampinvt_proto import AmpinvtProtocol 
from command_handler import CommandHandler
from ha_manager import HAManager
import mppt_register_map as rmap

# 全域變數
logger = None
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    """
    📖 讀取設定檔 (含強健的型別轉換邏輯)
    """
    try:
        with open("config.yaml", "r") as f: 
            config = yaml.safe_load(f)
        
        # 取得 modbus 區塊，若無則給空字典
        modbus = config.get('modbus', {})
        
        # 🟢 [強健設定讀取] 處理 unit_ids 多種可能的輸入格式
        # 無論使用者填 "1,2" (字串), 1 (數字), 還是 [1, 2] (列表)，都能正確解析
        raw = modbus.get('unit_ids', [1])

        if isinstance(raw, list):
            # 情境: [1, 2, "3"] -> [1, 2, 3]
            # 嘗試將列表中的每個元素轉為整數，過濾掉不合法的
            ids = []
            for x in raw:
                try: ids.append(int(x))
                except: pass
            modbus['unit_ids'] = ids if ids else [1]
            
        elif isinstance(raw, str):
            # 情境: "1, 2, 3" -> [1, 2, 3]
            modbus['unit_ids'] = [int(x) for x in raw.split(',') if x.strip().isdigit()]
            
        elif isinstance(raw, int):
            # 情境: 1 -> [1]
            modbus['unit_ids'] = [raw]
            
        else:
            # 情境: 格式不支援或為 None -> 使用預設值
            modbus['unit_ids'] = [1]

        # 確保回寫到 config 結構中
        config['modbus'] = modbus
            
        return config
    except Exception as e:
        print(f"❌ 設定檔讀取失敗: {e}")
        return None

def graceful_exit(signum, frame):
    """👋 優雅退場"""
    logger.info("🛑 收到關閉指令...")
    
    if app_config and ha_mgr and mqtt_client:
        # 如果設定了「結束時清除實體」
        if app_config.get('mqtt', {}).get('reset_discovery_on_exit'):
            logger.warning("🧹 清除 HA 實體...")
            try: 
                ha_mgr.clear_all_discovery(app_config['modbus']['unit_ids'])
                time.sleep(1)
            except: pass
            
    if mqtt_client:
        # 發送離線通知
        mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
        # mqtt_client.client.disconnect() # 視情況選用
        
    sys.exit(0)

def main():
    global mqtt_client, ha_mgr, app_config, logger
    
    # 1. 載入設定
    app_config = load_config()
    if not app_config: sys.exit(1)

    # 2. 初始化日誌
    debug_mode = app_config.get('system', {}).get('debug', False)
    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    
    logger.info("🚀 啟動 V5.6 穩定插隊版 (Robust Config + Socket Core)")
    
    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config.get('system', {})
    
    # 註冊關閉訊號
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    # 3. 初始化模組
    # 使用 RobustTCPClient (同步阻塞式) 確保物理層穩定
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    protocol = AmpinvtProtocol(tcp, debug=debug_mode)
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)
    
    # 初始化指令處理器 (傳入 ha_mgr 以便寫入後立即更新狀態)
    cmd_handler = CommandHandler(protocol, ha_mgr, timezone_offset=sys_cfg.get('timezone_offset', 8))

    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt_client.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)

    # 4. MQTT 連線與訂閱
    def on_mqtt_ready():
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        mqtt_client.publish(ha_mgr.availability_topic, "online", retain=True)
        # 訂閱所有控制主題
        for t in ["switch", "button", "number", "select"]:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        logger.info("👂 MQTT 準備就緒")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect()

    consecutive_errors = 0    
    MAX_ERRORS = 20
    offline_devices = {} # 黑名單機制 (時間戳)

    # 🟢 [核心邏輯] 處理指令函式
    def process_commands():
        """處理佇列中所有的 MQTT 指令"""
        count = 0
        while not mqtt_client.msg_queue.empty():
            msg = mqtt_client.msg_queue.get()
            
            # 資料解析
            if isinstance(msg, dict): t, p = msg.get('topic'), msg.get('payload')
            else: t, p = getattr(msg, 'topic', None), getattr(msg, 'payload', None)
            
            if not t or p is None: continue
            p_str = p.decode('utf-8').strip() if isinstance(p, bytes) else str(p).strip()

            logger.info(f"⚡ 插隊指令: {t} -> {p_str}")
            
            # 交給 Handler 處理 (含寫入、回讀更新)
            cmd_handler.process_message(t, p_str)
            count += 1
        return count

    # 5. 主迴圈
    while True:
        try:
            any_success = False 
            current_time = time.time()

            for uid in modbus_cfg['unit_ids']:
                # 🟢 [插隊機制] 在讀取每一台之前，先檢查有沒有指令要執行！
                # 這樣操作延遲最大只有「讀取一台設備的時間」(約 0.2~0.5s)
                if process_commands() > 0:
                    # 如果剛處理完指令，稍微休息一下讓總線緩衝
                    time.sleep(0.2)

                # --- 正常的輪詢邏輯 ---
                
                # A. 黑名單檢查
                if uid in offline_devices:
                    if current_time < offline_devices[uid]: 
                        continue #還在冷卻，跳過
                    else: 
                        logger.info(f"🔄 重試設備 #{uid}")

                try:
                    # B. 讀取數據
                    raw_data = protocol.read_b1_data(uid)
                    
                    if raw_data:
                        # C. 解碼與發布
                        vals = protocol.decode(raw_data, rmap.B1_INFO)
                        bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        
                        # 成功讀取，從黑名單移除
                        if uid in offline_devices: del offline_devices[uid]
                        any_success = True
                    
                    # 設備間隔
                    time.sleep(app_config['polling']['delay_between_units'])
                    
                except Exception:
                    # 讀取失敗，加入黑名單 (冷卻 60秒)
                    logger.warning(f"⚠️ 設備 #{uid} 讀取失敗")
                    offline_devices[uid] = current_time + 60
            
            # --- 看門狗邏輯 ---
            # 只要有一台成功，或是還有設備在黑名單中(代表不是全死)，就算系統正常
            if any_success or len(offline_devices) < len(modbus_cfg['unit_ids']):
                consecutive_errors = 0 
            else:
                consecutive_errors += 1 
                if consecutive_errors % 5 == 0:
                    logger.warning(f"⚠️ 全部連線失敗 ({consecutive_errors}/{MAX_ERRORS})")

            # 只有在連續全軍覆沒時才重啟
            if consecutive_errors >= MAX_ERRORS:
                logger.critical("❌ 系統嚴重故障 (RS485卡死)，強制重啟")
                mqtt_client.publish(ha_mgr.availability_topic, "offline", retain=True)
                sys.exit(1)

        except Exception as e:
            logger.error(f"主迴圈錯誤: {e}")
            consecutive_errors += 1
            
        # 每一輪結束休息
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
