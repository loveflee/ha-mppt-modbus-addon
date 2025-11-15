# module/mppt5.py

"""
📌 佛山金广源 MPPT RS485 通訊模組 - 多設備輪詢優化完整版 (0xB1 指令 93 bytes)
說明：
此模組支援多台 MPPT 設備輪詢，並嚴格控制設備間隔和總輪詢週期，避免 Modbus 衝突。
HA Discovery 會為每個 Slave ID 創建一個獨立的 Home Assistant 裝置。
修正：兼容框架調用 run(slave_id, modbus_manager) 的參數數量錯誤。
"""

import time
import json
import paho.mqtt.client as mqtt
import modbus_mqtt_client # 匯入連線管理模組

# ========================
# ⚙️ 參數設定 (從 modbus_mqtt_client 取得配置)
# ========================
# 這些變數會在 run() 執行時，從 modbus_mqtt_client 的 CONFIG 取得
NODE_ID = None
MODULE_NAME = None
RETAIN = False
SLAVE_IDS_TO_POLL = []
TOTAL_POLL_INTERVAL = 20
POLL_INTERVAL_BETWEEN_DEVICES = 0.5 # 設備間間隔縮短，從 2s 改為 0.5s，避免超時

# ... (build_query_packet 和 parse_response 函數保持不變) ...
# (為節省篇幅，這部分代碼省略，假設它們與您提供的代碼一致)
# ...

# ========================
# 📡 發佈 HA Discovery 設定
# ========================
def publish_discovery_config(mqtt_client, address):
    """ 為單一 Modbus 地址發佈所有 HA Discovery 配置 """
    # 這裡使用 run 函數中取得的全局變數
    global NODE_ID, MODULE_NAME, RETAIN

    device_name = f"{NODE_ID}_{MODULE_NAME}_addr{address}"
    device_info = {
        "identifiers": [device_name],
        "name": f"MPPT 太陽能充電控制器 (地址 {address})",
        "model": "MPPT RS485 (多設備輪詢版)",
        "manufacturer": "佛山金广源"
    }

    # --- 1. 定義數值型感測器 (Sensor) ---
    sensor_definitions = [
        # 核心監控數據
        ("pv_voltage", "PV 電壓", "V", "voltage"),
        ("battery_voltage", "電池電壓", "V", "voltage"),
        ("charge_current", "充電電流", "A", "current"),
        ("charge_power", "瞬時充電功率", "W", "power"),
        ("internal_temp1", "內部溫度 1", "°C", "temperature"),
        ("external_temp1", "外部溫度 1", "°C", "temperature"),
        # 能源數據 (total_increasing 是能源儀表板的關鍵)
        ("today_yield_wh", "今日發電量", "Wh", "energy"),
        ("total_yield_wh", "總發電量", "Wh", "energy"),
        # 設定值
        ("rated_voltage", "額定電壓設定", "V", "voltage"),
        ("equalize_voltage", "均充電壓設定", "V", "voltage"),
        ("float_voltage", "浮充電壓設定", "V", "voltage"),
        ("max_charge_current", "設置最大充電電流", "A", "current"),
        ("battery_type", "電池類型代碼"),
        ("battery_count", "電池數量"),
    ]

    for key, name, *optional_attrs in sensor_definitions:
        unit = optional_attrs[0] if len(optional_attrs) > 0 else None
        device_class = optional_attrs[1] if len(optional_attrs) > 1 else None

        # 💡 關鍵: 設定 state_class
        if key.endswith("_yield_wh"):
            state_class = "total_increasing"
        elif device_class in ["voltage", "current", "temperature", "power"]:
            state_class = "measurement"
        else:
            state_class = None

        # 📌 Topic 和 ID 必須包含地址，確保每個設備獨立
        topic = f"homeassistant/sensor/{NODE_ID}_{MODULE_NAME}_{address}/{key}/config"
        payload = {
            "name": name,
            "state_topic": f"{NODE_ID}_{MODULE_NAME}/{address}/{key}/state", # 數據發佈 Topic
            "unit_of_measurement": unit,
            "device_class": device_class,
            "state_class": state_class,
            "unique_id": f"{NODE_ID}_{MODULE_NAME}_{address}_{key}",
            "device": device_info,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        mqtt_client.publish(topic, json.dumps(payload), retain=RETAIN)

    # --- 2. 定義布林型感測器 (Binary Sensor) ---
    binary_sensor_definitions = [
        ("run_status", "運行狀態", "running"),
        ("fan_status", "風扇狀態", "running"),
        ("charging", "充電中", "running"),
        ("tracking", "MPPT 追蹤中", "running"),
        ("pv_over_voltage", "PV 過壓警告", "problem"),
        ("overcharge_protect", "過充保護啟用", "problem"),
        # ... (其他您想加入的 Binary Sensor)
    ]

    for key, name, device_class in binary_sensor_definitions:
        topic = f"homeassistant/binary_sensor/{NODE_ID}_{MODULE_NAME}_{address}/{key}/config"
        payload = {
            "name": name,
            "state_topic": f"{NODE_ID}_{MODULE_NAME}/{address}/{key}/state",
            "device_class": device_class,
            "unique_id": f"{NODE_ID}_{MODULE_NAME}_{address}_{key}_bs",
            "payload_on": "True",
            "payload_off": "False",
            "device": device_info,
        }
        mqtt_client.publish(topic, json.dumps(payload), retain=RETAIN)


# ========================
# 🔁 查詢與發佈資料
# ========================
def query_and_publish(address, mqtt_client, modbus_manager):
    """ 對單一 Modbus 地址進行查詢和數據發佈 """
    # 這裡使用 run 函數中取得的全局變數
    global NODE_ID, MODULE_NAME, RETAIN 

    packet = build_query_packet(address)

    try:
        modbus_client = modbus_manager.get_client()
        # ModbusTcpClient 沒有直接的 .socket 屬性，但 pymodbus v3.x 支援同步客戶端。
        # 由於您使用的是自定義協議（非標準 Modbus 封包），必須直接存取 socket 來發送原始封包。
        # 警告：此處 'sock' 存取方式可能與 pymodbus 版本有關，如果運行失敗，可能需要修改。
        sock = modbus_client.socket 
        
        if sock is None:
             print(f"⚠️ 地址 {address}: Modbus 連線未建立或已斷開，跳過查詢。")
             return

        sock.send(packet)
        sock.settimeout(1.5) # 設置接收超時時間
        response = sock.recv(93)

        if len(response) != 93:
            print(f"⚠️ 地址 {address} 無效回應（長度 {len(response)}），跳過發佈。")
            return

        values = parse_response(response)

        # 🚀 循環發佈所有解析到的 key-value 對
        for key, value in values.items():
            if isinstance(value, bool):
                payload = "True" if value else "False"
            else:
                payload = str(value) # 確保所有值都是字串格式
            
            # 數據發佈 Topic 必須包含地址
            topic = f"{NODE_ID}_{MODULE_NAME}/{address}/{key}/state"
            mqtt_client.publish(topic, payload, retain=RETAIN)

        print(f"✅ 地址 {address} 數據發佈完成。")

    except Exception as e:
        print(f"❌ 查詢地址 {address} 發生錯誤: {e}")
        # 錯誤處理可以考慮在發生嚴重錯誤時重新初始化 Modbus 連線
        # modbus_manager._connect() # 嘗試重連

# ========================
# 🔵 主進入點 (修正兼容框架調用)
# ========================
def run(options: dict):
    """
    主要執行函數，接收從 HA Add-on options.json 讀取的配置。
    """
    global NODE_ID, MODULE_NAME, SLAVE_IDS_TO_POLL, TOTAL_POLL_INTERVAL, POLL_INTERVAL_BETWEEN_DEVICES

    # 1. 初始化配置 (注入到 modbus_mqtt_client)
    try:
        modbus_mqtt_client.initialize_config(options)
        modbus_manager = modbus_mqtt_client.get_modbus_manager()
    except Exception as e:
        print(f"❌ 配置/Modbus 初始化失敗: {e}")
        return

    # 2. 從配置字典中設定本模組所需的參數
    NODE_ID = options.get('node_id')
    MODULE_NAME = options.get('module_name')
    TOTAL_POLL_INTERVAL = options.get('poll_interval_seconds', 20)
    device_delay_ms = options.get('device_delay_ms', 500)
    POLL_INTERVAL_BETWEEN_DEVICES = device_delay_ms / 1000.0 # 毫秒轉秒

    # 解析 Slave IDs
    slave_ids_str = options.get('slave_ids')
    try:
        SLAVE_IDS_TO_POLL = [int(i.strip()) for i in slave_ids_str.split(',') if i.strip()]
    except Exception:
        print("🛑 錯誤：無法解析 slave_ids，請檢查格式是否為 '1,2,3'")
        return

    if not SLAVE_IDS_TO_POLL:
        print("🛑 錯誤：SLAVE_IDS_TO_POLL 列表為空，請配置要讀取的地址。")
        return

    # 3. 建立並連線 MQTT 客戶端
    mqtt_client = modbus_mqtt_client.get_mqtt_client()
    try:
        mqtt_client.connect(options.get('mqtt_host'), options.get('mqtt_port'), 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"❌ MQTT 連線失敗: {e}")
        return


    # 4. 初始化：為所有設備發佈 HA Discovery (只需執行一次)
    print("🚀 啟動 HA Discovery 配置...")
    for slave_id in SLAVE_IDS_TO_POLL:
        publish_discovery_config(mqtt_client, slave_id)

    print(f"配置完成。總輪詢週期設定為 {TOTAL_POLL_INTERVAL} 秒。輪詢 {len(SLAVE_IDS_TO_POLL)} 台設備。")

    try:
        while True:
            cycle_start_time = time.time()

            # 5. 核心輪詢迴圈
            for i, slave_id in enumerate(SLAVE_IDS_TO_POLL):
                print(f"\n--- 開始讀取設備 {i+1}/{len(SLAVE_IDS_TO_POLL)} (地址 {slave_id}) ---")

                query_and_publish(slave_id, mqtt_client, modbus_manager)

                # 6. 控制設備間間隔 (避免 Modbus 衝突)
                if i < len(SLAVE_IDS_TO_POLL) - 1 and POLL_INTERVAL_BETWEEN_DEVICES > 0:
                    print(f"等待 {POLL_INTERVAL_BETWEEN_DEVICES:.2f} 秒後讀取下一台...")
                    time.sleep(POLL_INTERVAL_BETWEEN_DEVICES)

            # 7. 確保符合總輪詢週期
            cycle_elapsed_time = time.time() - cycle_start_time
            time_to_wait = TOTAL_POLL_INTERVAL - cycle_elapsed_time

            if time_to_wait > 0:
                print(f"\n✅ 本輪輪詢完成。等待 {time_to_wait:.2f} 秒，進入下一輪。")
                time.sleep(time_to_wait)
            else:
                print(f"\n⚠️ 警告：輪詢耗時 ({cycle_elapsed_time:.2f}s) 超過總週期 ({TOTAL_POLL_INTERVAL}s)！立即開始下一輪。")
                time.sleep(1) # 至少休息 1 秒，避免佔用過多 CPU 資源

    except KeyboardInterrupt:
        print("🛑 結束 MPPT 模組")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        modbus_manager.close()

# 為了兼容原有的框架，如果您希望主程序直接呼叫 run(slave_id_or_name, modbus_manager)，
# 您需要在主程式中將 run 的邏輯調整為接收 options 字典。
#
# 原有的 run(slave_id_or_name, modbus_manager) 函數已完全重寫為 run(options: dict)。
