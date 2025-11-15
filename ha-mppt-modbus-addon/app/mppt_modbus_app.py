"""
可運行之舊版mppt5
佛山金广源 MPPT RS485 通訊模組 - 多設備輪詢優化完整版 (0xB1 指令 93 bytes)
說明：
此模組支援多台 MPPT 設備輪詢，並嚴格控制設備間隔和總輪詢週期，避免 Modbus 衝突。
它從 run(options) 接收 HA Add-on 配置。
"""

import time
import json
import paho.mqtt.client as mqtt
# 引入 Modbus/MQTT 連線管理模組，所有連線操作都在此模組中完成
import modbus_mqtt_client 
from typing import Dict, Any, List

# 全局變數用於儲存從 options 傳入的配置（在 run() 中初始化）
CONFIG: Dict[str, Any] = {}


# ========================
# 🧱 建立查詢封包 (8 bytes)
# ========================
def build_query_packet(address: int) -> bytes:
    """ 建立查詢封包：地址 + 0xB1 + 0x01 + [0x00,0x00,0x00,0x00] + 校驗 """
    packet = bytearray([address, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
    # 計算校驗碼 (前 7 個字節相加後取最低 8 位)
    checksum = sum(packet[:7]) & 0xFF
    packet[7] = checksum
    return bytes(packet)

# ========================
# 📖 解析 MPPT 回傳資料 (完整解析所有欄位)
# ========================
def parse_response(data: bytes) -> dict:
    """ 根據 PDF 協議，解析 93 bytes 回傳的所有欄位，並計算衍生值。 """
    if len(data) != 93:
        # 如果收到錯誤長度的數據，拋出異常
        raise ValueError(f"回應資料長度錯誤：收到 {len(data)} bytes，應為 93")

    result = {}

    # --- 💡 輔助函數 ---
    def word_to_float(high, low, scale):
        # 將兩個 byte (高位, 低位) 組合成一個 16-bit 數值，然後除以 scale
        return ((high << 8) | low) / scale
    
    def dword_to_int(d4, d3, d2, d1):
        # 將四個 byte 組合成一個 32-bit 整數
        return (d4 << 24) | (d3 << 16) | (d2 << 8) | d1

    # ========== 1️⃣ 狀態位 (Byte 3, 4, 5) - Binary Sensor ==========
    result.update({
        "run_status": bool(data[3] & 0x01),        # 運行狀態 (開/關)
        "fan_status": bool(data[3] & 0x04),        # 風扇狀態
        "temp_status": bool(data[3] & 0x08),       # 溫度保護
        "int_temp1_fault": bool(data[3] & 0x20),   # 內部溫度1異常
        "charging": bool(data[4] & 0x01),          # 充電中
        "equalizing_charge": bool(data[4] & 0x02), # 均充
        "tracking": bool(data[4] & 0x04),          # MPPT跟蹤
        "float_charge": bool(data[4] & 0x08),      # 浮充
        "charge_limited": bool(data[4] & 0x10),    # 充電限流
        "pv_over_voltage": bool(data[4] & 0x80),   # PV過壓
        "load_output": bool(data[5] & 0x02),       # 負載輸出
        "overcharge_protect": bool(data[5] & 0x10),# 過充保護
        "overvoltage_protect": bool(data[5] & 0x20)# 過壓保護
    })

    # ========== 2️⃣ 系統參數 & 設定值 (Sensor) ==========
    result.update({
        "battery_type": data[8],                   # 電池類型 (代碼)
        "battery_count": data[10],                 # 電池數量 (串聯顆數)
        "rated_voltage": word_to_float(data[16], data[17], 100),       # 額定電壓設定 (V)
        "equalize_voltage": word_to_float(data[18], data[19], 100),    # 均充電壓設定 (V)
        "float_voltage": word_to_float(data[20], data[21], 100),       # 浮充電壓設定 (V)
        "max_charge_current": word_to_float(data[26], data[27], 100),   # 設置最大充電電流 (A)
    })

    # ========== 3️⃣ 實際測量值 (Sensor) ==========
    result.update({
        "pv_voltage": word_to_float(data[30], data[31], 10),           # 實際 PV 電壓 (V)
        "battery_voltage": word_to_float(data[32], data[33], 100),     # 實際電池電壓 (V)
        "charge_current": word_to_float(data[34], data[35], 100),      # 實際充電電流 (A)
        "internal_temp1": word_to_float(data[36], data[37], 10),       # 內部溫度 (°C)
        "external_temp1": word_to_float(data[40], data[41], 100),      # 外部溫度 (°C)
    })

    # ========== 4️⃣ 發電量 (Wh) ==========
    result.update({
        "today_yield_wh": dword_to_int(data[44], data[45], data[46], data[47]), # 今日累積發電量 (Wh)
        "total_yield_wh": dword_to_int(data[48], data[49], data[50], data[51]), # 總歷史發電量 (Wh)
    })
    
    # 💡 優化新增：計算瞬時充電功率 (W)
    # 功率 (W) = 電壓 (V) * 電流 (A)
    try:
        charge_power = result["battery_voltage"] * result["charge_current"]
        result["charge_power"] = round(charge_power, 2)
    except KeyError:
        # 如果電壓或電流解析失敗，則不計算功率
        result["charge_power"] = 0.0
    
    return result

# ========================
# 📡 發佈 HA Discovery 設定
# ========================
def publish_discovery_config(mqtt_client: mqtt.Client, address: int):
    """ 為單一 Modbus 地址發佈所有 HA Discovery 配置 """
    # 從 CONFIG 獲取配置 (這些是從 options.json 讀取的)
    node_id = CONFIG.get("node_id", "default_node")
    module_name = CONFIG.get("module_name", "mppt")
    # HA Add-on 配置中的 retain 預設為 False
    retain = CONFIG.get("retain", False) 
    
    device_name = f"{node_id}_{module_name}_addr{address}"
    device_info = {
        "identifiers": [device_name],
        "name": f"MPPT 太陽能充電控制器 (地址 {address})", 
        "model": "MPPT RS485 (多設備輪詢版)",
        "manufacturer": "佛山金广源"
    }

    # --- 1. 定義數值型感測器 (Sensor) ---
    sensor_definitions = [
        ("pv_voltage", "PV 電壓", "V", "voltage"),
        ("battery_voltage", "電池電壓", "V", "voltage"),
        ("charge_current", "充電電流", "A", "current"),
        ("charge_power", "瞬時充電功率", "W", "power"), 
        ("internal_temp1", "內部溫度 1", "°C", "temperature"),
        ("external_temp1", "外部溫度 1", "°C", "temperature"),
        ("today_yield_wh", "今日發電量", "Wh", "energy"),
        ("total_yield_wh", "總發電量", "Wh", "energy"),
        ("rated_voltage", "額定電壓設定", "V", "voltage"),
        ("equalize_voltage", "均充電壓設定", "V", "voltage"),
        ("float_voltage", "浮充電壓設定", "V", "voltage"),
        ("max_charge_current", "設置最大充電電流", "A", "current"),
        ("battery_type", "電池類型代碼", None, None),
        ("battery_count", "電池數量", None, None),
    ]
    
    for key, name, unit, device_class in sensor_definitions:
        
        # 💡 關鍵: 設定 state_class
        if key.endswith("_yield_wh"):
            # total_increasing 用於能源儀表板
            state_class = "total_increasing" 
        elif device_class in ["voltage", "current", "temperature", "power"]:
            state_class = "measurement"
        else:
            state_class = None 

        # 📌 Topic 和 ID 必須包含地址，確保每個設備獨立
        topic = f"homeassistant/sensor/{node_id}_{module_name}_{address}/{key}/config"
        payload = {
            "name": name,
            "state_topic": f"{node_id}_{module_name}/{address}/{key}/state", # 數據發佈 Topic
            "unit_of_measurement": unit,
            "device_class": device_class,
            "state_class": state_class,
            "unique_id": f"{node_id}_{module_name}_{address}_{key}",
            "device": device_info,
        }
        # 移除值為 None 的屬性，確保 JSON 乾淨
        payload = {k: v for k, v in payload.items() if v is not None} 
        mqtt_client.publish(topic, json.dumps(payload), retain=retain)
    
    # --- 2. 定義布林型感測器 (Binary Sensor) ---
    binary_sensor_definitions = [
        ("run_status", "運行狀態", "running"),
        ("fan_status", "風扇狀態", "running"),
        ("charging", "充電中", "running"),
        ("tracking", "MPPT 追蹤中", "running"),
        ("pv_over_voltage", "PV 過壓警告", "problem"),
        ("overcharge_protect", "過充保護啟用", "problem"),
    ]
    
    for key, name, device_class in binary_sensor_definitions:
        topic = f"homeassistant/binary_sensor/{node_id}_{module_name}_{address}/{key}/config"
        payload = {
            "name": name,
            "state_topic": f"{node_id}_{module_name}/{address}/{key}/state",
            "device_class": device_class,
            "unique_id": f"{node_id}_{module_name}_{address}_{key}_bs",
            "payload_on": "True",
            "payload_off": "False",
            "device": device_info,
        }
        mqtt_client.publish(topic, json.dumps(payload), retain=retain)


# ========================
# 🔁 查詢與發佈資料
# ========================
def query_and_publish(address: int, mqtt_client: mqtt.Client, modbus_manager: modbus_mqtt_client.ModbusManager):
    """ 對單一 Modbus 地址進行查詢和數據發佈 """
    # 從 CONFIG 獲取配置
    node_id = CONFIG.get("node_id", "default_node")
    module_name = CONFIG.get("module_name", "mppt")
    retain = CONFIG.get("retain", False)
    
    packet = build_query_packet(address)
    
    try:
        # 透過 ModbusManager 獲取 client 實例，它會自動處理重連
        modbus_client = modbus_manager.get_client()
        sock = modbus_client.socket
        
        if sock is None:
             print(f"⚠️ 地址 {address}: Modbus 連線未建立或已斷開，跳過查詢。")
             return

        # 核心 Modbus 通訊：直接使用 socket 進行原始封包傳輸 (非標準 Modbus)
        sock.send(packet)
        # 必須設置超時，否則程式可能會阻塞
        sock.settimeout(1.5) 
        response = sock.recv(93)

        if len(response) != 93:
            print(f"⚠️ 地址 {address} 無效回應（長度 {len(response)}），跳過發佈。")
            return

        values = parse_response(response)
        
        # 🚀 循環發佈所有解析到的 key-value 對
        for key, value in values.items():
            if isinstance(value, bool):
                # 布林值轉為字串 "True" 或 "False" 供 MQTT 傳輸
                payload = "True" if value else "False"
            else:
                # 其他數值轉為字串
                payload = str(value)

            # 數據發佈 Topic 必須包含地址
            topic = f"{node_id}_{module_name}/{address}/{key}/state"
            mqtt_client.publish(topic, payload, retain=retain)
                
        print(f"✅ 地址 {address} 數據發佈完成。")

    except Exception as e:
        # 捕捉所有異常，包括 socket 超時、連線錯誤等
        print(f"❌ 查詢地址 {address} 發生錯誤: {e}")


# ========================
# 🔵 主進入點 (接收 options 字典)
# ========================
def run(options: dict):
    """
    主要執行函數。接收 HA Add-on options.json 讀取的配置字典。
    """
    global CONFIG
    CONFIG = options # 將配置儲存到全局變數，供其他函數使用

    # 1. 解析和設置運行參數
    try:
        # 從 options 字典中讀取參數，並轉換為 Python 列表和數值
        slave_ids_str: str = options.get('slave_ids', '1').strip()
        SLAVE_IDS_TO_POLL: List[int] = [int(i.strip()) for i in slave_ids_str.split(',') if i.strip()]
        TOTAL_POLL_INTERVAL: int = options.get('poll_interval_seconds', 20)
        device_delay_ms: int = options.get('device_delay_ms', 500)
        # 毫秒轉秒 
        POLL_INTERVAL_BETWEEN_DEVICES: float = device_delay_ms / 1000.0 

        if not SLAVE_IDS_TO_POLL:
            print("🛑 錯誤：請配置要讀取的 Modbus Slave 地址。")
            return
    except Exception as e:
        print(f"🛑 錯誤：配置格式錯誤 (例如 slave_ids 或 poll_interval_seconds): {e}")
        return

    # 2. 初始化 Modbus Manager
    try:
        # 初始化 modbus_mqtt_client 模組中的 CONFIG 並建立 ModbusManager 實例
        modbus_mqtt_client.initialize_config(options) 
        modbus_manager = modbus_mqtt_client.get_modbus_manager()
    except Exception as e:
        print(f"❌ Modbus 連線初始化失敗: {e}")
        return

    # 3. 連線 MQTT
    try:
        mqtt_client = modbus_mqtt_client.get_mqtt_client()
        # 嘗試連線（非阻塞）
        mqtt_client.connect(CONFIG.get('mqtt_host'), CONFIG.get('mqtt_port'), 60)
        # 啟動非阻塞網路循環
        mqtt_client.loop_start() 
    except Exception as e:
        print(f"❌ MQTT 客戶端建立失敗: {e}")
        return

    # 4. 初始化：為所有設備發佈 HA Discovery (只需執行一次)
    print("🚀 啟動 HA Discovery 配置...")
    for slave_id in SLAVE_IDS_TO_POLL:
        publish_discovery_config(mqtt_client, slave_id)
        
    print(f"配置完成。總輪詢週期設定為 {TOTAL_POLL_INTERVAL} 秒。輪詢 {len(SLAVE_IDS_TO_POLL)} 台設備。")

    try:
        while True: # 主循環，永不停止
            cycle_start_time = time.time()
            
            # 5. 核心輪詢迴圈
            for i, slave_id in enumerate(SLAVE_IDS_TO_POLL):
                print(f"\n--- 開始讀取設備 {i+1}/{len(SLAVE_IDS_TO_POLL)} (地址 {slave_id}) ---")
                
                query_and_publish(slave_id, mqtt_client, modbus_manager) 
                
                # 6. 控制設備間間隔 (避免 Modbus 衝突)
                if i < len(SLAVE_IDS_TO_POLL) - 1:
                    print(f"等待 {POLL_INTERVAL_BETWEEN_DEVICES:.2f} 秒後讀取下一台...")
                    time.sleep(POLL_INTERVAL_BETWEEN_DEVICES) 
            
            # 7. 確保符合總輪詢週期
            cycle_elapsed_time = time.time() - cycle_start_time
            time_to_wait = TOTAL_POLL_INTERVAL - cycle_elapsed_time
            
            if time_to_wait > 0:
                print(f"\n✅ 本輪輪詢完成。等待 {time_to_wait:.2f} 秒，進入下一輪。")
                time.sleep(time_to_wait)
            else:
                # 如果超時，至少等待 1 秒以避免 CPU 佔用過高
                print(f"\n⚠️ 警告：輪詢耗時 ({cycle_elapsed_time:.2f}s) 超過總週期 ({TOTAL_POLL_INTERVAL}s)！至少等待 1 秒。")
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("🛑 結束 MPPT 模組")
    except Exception as e:
        print(f"❌ 主循環發生嚴重例外: {e}")
    finally:
        # 清理連線
        print("清理連線中...")
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        except:
            pass
        try:
            modbus_manager.close() # 關閉 Modbus 連線
        except:
            pass
        print("清理完成。程式退出。")
