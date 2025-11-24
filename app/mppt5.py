"""
📌 佛山金廣源 MPPT RS485 通訊模組 - 多設備輪詢優化完整版
說明：
此版本基於舊版代碼的 **完整 Modbus 協議邏輯**，重構成 Python 類別 (MPPTPoller)，移除了所有全局變數，提升代碼維護性。
修正了 Modbus 查詢封包，包含正確的 8 bytes 格式和校驗碼，以解決超時問題。
支援多台 MPPT 設備輪詢，並嚴格控制設備間隔和總輪詢週期。
HA Discovery 會為每個 Slave ID 創建一個獨立的 Home Assistant 裝置。

💡 優化日誌輸出：移除冗餘的單設備成功訊息，改為週期性輸出精簡的輪詢結果摘要。
"""

import time
import json
import paho.mqtt.client as mqtt
import modbus_mqtt_client
import sys # 用於日誌輸出
from typing import Dict, Any, List

# ========================
# ⚙️ 參數設定與感測器集中映射表 (常量)
# ========================

# 數值型感測器定義 (Key: (名稱, 單位, device_class, state_class))
SENSOR_MAPPING = {
    # 核心監控數據
    "pv_voltage": ("PV 電壓", "V", "voltage", "measurement"),
    "battery_voltage": ("電池電壓", "V", "voltage", "measurement"),
    "charge_current": ("充電電流", "A", "current", "measurement"),
    "charge_power": ("瞬時充電功率", "W", "power", "measurement"), # 這是計算出來的值
    "internal_temp1": ("內部溫度 1", "°C", "temperature", "measurement"),
    "external_temp1": ("外部溫度 1", "°C", "temperature", "measurement"),
    # 能源數據 (total_increasing 是能源儀表板的關鍵)
    "today_yield_wh": ("今日發電量", "Wh", "energy", "total_increasing"),
    "total_yield_wh": ("總發電量", "Wh", "energy", "total_increasing"),
    # 設定值/狀態值
    "rated_voltage": ("額定電壓設定", "V", "voltage", "measurement"),
    "equalize_voltage": ("均充電壓設定", "V", "voltage", "measurement"),
    "float_voltage": ("浮充電壓設定", "V", "voltage", "measurement"),
    "max_charge_current": ("設置最大充電電流", "A", "current", "measurement"),
    "battery_type": ("電池類型代碼", None, None, None),
    "battery_count": ("電池數量", None, None, None),
}

# 布林型感測器定義 (Key: (名稱, device_class))
BINARY_SENSOR_MAPPING = {
    "run_status": ("運行狀態", "running"),
    "fan_status": ("風扇狀態", "running"),
    "charging": ("充電中", "running"),
    "equalizing_charge": ("均充中", "running"),
    "float_charge": ("浮充中", "running"),
    "tracking": ("MPPT 追蹤中", "running"),
    "charge_limited": ("充電限流", "running"),
    "load_output": ("負載輸出", "running"),
    "pv_over_voltage": ("PV 過壓警告", "problem"),
    "overcharge_protect": ("過充保護啟用", "problem"),
    "overvoltage_protect": ("過壓保護", "problem"),
    "temp_status": ("溫度保護啟用", "problem"),
    "int_temp1_fault": ("內部溫度1異常", "problem"),
}

# ========================
# 📦 MPPTPoller 類別 (核心邏輯)
# ========================
class MPPTPoller:

    def __init__(self, options: dict, modbus_manager, mqtt_client):
        """
        初始化 MPPTPoller 實例，儲存所有配置和客戶端。
        """
        # 配置屬性
        self.node_id = options.get('node_id', 'default_node')
        self.module_name = options.get('module_name', 'mppt')
        self.retain = options.get('mqtt_retain', False)
        self.total_poll_interval = options.get('poll_interval_seconds', 20)
        device_delay_ms = options.get('device_delay_ms', 500)
        self.poll_interval_between_devices = device_delay_ms / 1000.0

        # 連線實例
        self.modbus_manager = modbus_manager
        self.mqtt_client = mqtt_client

        # 解析 Slave IDs
        slave_ids_str = options.get('slave_ids', '').strip()
        try:
            self.slave_ids_to_poll = [int(i.strip()) for i in slave_ids_str.split(',') if i.strip()]
        except ValueError:
            print("🛑 錯誤：無法解析 slave_ids，請檢查格式是否為 '1,2,3'", file=sys.stderr)
            self.slave_ids_to_poll = []

        if not self.slave_ids_to_poll:
            print("🛑 錯誤：SLAVE_IDS_TO_POLL 列表為空，請配置要讀取的地址。", file=sys.stderr)

        self.device_info_base = {
            "model": "ampinvt RS485 (多設備輪詢版)",
            "manufacturer": "ampinvt"
        }

    # ========================
    # 🛠️ Modbus 協定處理 (從舊版複製過來的準確協議)
    # ========================

    def _build_query_packet(self, address: int) -> bytes:
        """ 
        [修正] 建立查詢封包：地址 + 0xB1 + 0x01 + [0x00,0x00,0x00,0x00] + 校驗 (共 8 bytes) 
        這個封包格式應與設備製造商提供的協議一致。
        """
        packet = bytearray([address, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        # 計算校驗碼 (前 7 個字節相加後取最低 8 位)
        checksum = sum(packet[:7]) & 0xFF
        packet[7] = checksum
        return bytes(packet)

    def _parse_response(self, data: bytes) -> dict:
        """ 
        [修正] 根據 PDF 協議，解析 93 bytes 回傳的所有欄位，並計算衍生值。
        此邏輯從舊版詳細解析中移植。
        """
        if len(data) != 93:
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
            "run_status": bool(data[3] & 0x01),      # 運行狀態 (開/關)
            "fan_status": bool(data[3] & 0x04),      # 風扇狀態
            "temp_status": bool(data[3] & 0x08),     # 溫度保護
            "int_temp1_fault": bool(data[3] & 0x20), # 內部溫度1異常
            "charging": bool(data[4] & 0x01),        # 充電中
            "equalizing_charge": bool(data[4] & 0x02), # 均充
            "tracking": bool(data[4] & 0x04),        # MPPT跟蹤
            "float_charge": bool(data[4] & 0x08),    # 浮充
            "charge_limited": bool(data[4] & 0x10),  # 充電限流
            "pv_over_voltage": bool(data[4] & 0x80), # PV過壓
            "load_output": bool(data[5] & 0x02),     # 負載輸出
            "overcharge_protect": bool(data[5] & 0x10),# 過充保護
            "overvoltage_protect": bool(data[5] & 0x20)# 過壓保護
        })

        # ========== 2️⃣ 系統參數 & 設定值 (Sensor) ==========
        result.update({
            "battery_type": data[8],                 # 電池類型 (代碼)
            "battery_count": data[10],               # 電池數量 (串聯顆數)
            "rated_voltage": word_to_float(data[16], data[17], 100),       # 額定電壓設定 (V)
            "equalize_voltage": word_to_float(data[18], data[19], 100),    # 均充電壓設定 (V)
            "float_voltage": word_to_float(data[20], data[21], 100),       # 浮充電壓設定 (V)
            "max_charge_current": word_to_float(data[26], data[27], 100),  # 設置最大充電電流 (A)
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
        try:
            charge_power = result["battery_voltage"] * result["charge_current"]
            result["charge_power"] = round(charge_power, 2)
        except KeyError:
            result["charge_power"] = 0.0
        
        return result

    # ========================
    # 📡 發佈 HA Discovery 設定
    # ========================

    def _publish_discovery_config(self, address: int):
        """ 為單一 Modbus 地址發佈所有 HA Discovery 配置 """
        
        device_name = f"{self.node_id}_{self.module_name}_addr{address}"
        device_info = self.device_info_base.copy()
        device_info.update({
            "identifiers": [device_name],
            "name": f"MPPT 太陽能控制器 (地址 {address})",
        })

        # --- 1. 定義數值型感測器 (Sensor) ---
        for key, (name, unit, device_class, _) in SENSOR_MAPPING.items():
            
            # 💡 根據 Key 設定 state_class
            if key.endswith("_yield_wh"):
                state_class = "total_increasing" # 能源儀表板
            elif device_class in ["voltage", "current", "temperature", "power"]:
                state_class = "measurement"
            else:
                state_class = None

            topic = f"homeassistant/sensor/{self.node_id}_{self.module_name}_{address}/{key}/config"
            payload = {
                "name": name,
                "state_topic": f"{self.node_id}_{self.module_name}/{address}/{key}/state",
                "unit_of_measurement": unit,
                "device_class": device_class,
                "state_class": state_class,
                "unique_id": f"{self.node_id}_{self.module_name}_{address}_{key}",
                "device": device_info,
            }
            # 移除 None 值
            payload = {k: v for k, v in payload.items() if v is not None}
            self.mqtt_client.publish(topic, json.dumps(payload), retain=self.retain)

        # --- 2. 定義布林型感測器 (Binary Sensor) ---
        for key, (name, device_class) in BINARY_SENSOR_MAPPING.items():
            topic = f"homeassistant/binary_sensor/{self.node_id}_{self.module_name}_{address}/{key}/config"
            payload = {
                "name": name,
                "state_topic": f"{self.node_id}_{self.module_name}/{address}/{key}/state",
                "device_class": device_class,
                "unique_id": f"{self.node_id}_{self.module_name}_{address}_{key}_bs",
                "payload_on": "True",
                "payload_off": "False",
                "device": device_info,
            }
            self.mqtt_client.publish(topic, json.dumps(payload), retain=self.retain)

    # ========================
    # 🔁 查詢與發佈資料
    # ========================

    def _query_and_publish(self, address: int) -> str:
        """ 
        對單一 Modbus 地址進行查詢和數據發佈，並返回狀態 (OK, FAIL, TOUT)。
        此函數不再輸出成功日誌。
        """
        
        packet = self._build_query_packet(address)

        try:
            modbus_client = self.modbus_manager.get_client()
            # 直接存取 .socket 進行原始封包通訊
            sock = modbus_client.socket 
            
            if sock is None:
                # 僅在發生問題時輸出，不重複連線狀態
                print(f"⚠️ 地址 {address}: Modbus 連線未建立或已斷開，跳過查詢。", file=sys.stderr)
                return "FAIL"

            # 核心 Modbus 通訊
            sock.send(packet)
            # 設置接收超時時間 (2.0 秒)
            sock.settimeout(2.0) 
            
            # 預期接收 93 bytes
            response = sock.recv(93)

            if len(response) != 93:
                print(f"⚠️ 地址 {address} 無效回應（長度 {len(response)}），跳過發佈。", file=sys.stderr)
                return "FAIL"
            
            # TODO: 實際應用中，請在此處加入 Checksum/CRC 驗證

            values = self._parse_response(response)

            # 🚀 循環發佈所有解析到的 key-value 對
            for key, value in values.items():
                
                # 只發佈在映射表中定義的 key
                if key not in SENSOR_MAPPING and key not in BINARY_SENSOR_MAPPING:
                    continue 

                if isinstance(value, bool):
                    payload = "True" if value else "False"
                else:
                    payload = str(value)
                
                # 數據發佈 Topic 必須包含地址
                topic = f"{self.node_id}_{self.module_name}/{address}/{key}/state"
                self.mqtt_client.publish(topic, payload, retain=self.retain)

            # 成功時不再輸出日誌，僅返回狀態
            return "OK"

        except Exception as e:
            # 捕捉所有異常，包括 socket 超時 (timed out)
            status = "ERR" # Default error status
            if "timed out" in str(e):
                 status = "TOUT"
            print(f"❌ 查詢地址 {address} 發生錯誤: {e}", file=sys.stderr)
            return status

    # ========================
    # 🏃 主輪詢迴圈
    # ========================

    def start_polling(self):
        """ 啟動輪詢與發佈的無限迴圈 """

        if not self.slave_ids_to_poll:
            print("❌ 未配置任何設備地址，停止輪詢。", file=sys.stderr)
            return

        # 1. 初始化：為所有設備發佈 HA Discovery (只需執行一次)
        print("🚀 啟動 HA Discovery 配置...")
        for slave_id in self.slave_ids_to_poll:
            self._publish_discovery_config(slave_id)

        print(f"配置完成。總輪詢週期設定為 {self.total_poll_interval} 秒。輪詢 {len(self.slave_ids_to_poll)} 台設備。")

        try:
            while True:
                cycle_start_time = time.time()
                
                device_statuses = [] # 收集本輪的輪詢結果

                # 2. 核心輪詢迴圈
                for i, slave_id in enumerate(self.slave_ids_to_poll):
                    
                    status = self._query_and_publish(slave_id)
                    device_statuses.append(f"({slave_id}:{status})") # 記錄結果 e.g. (4:OK)

                    # 3. 控制設備間間隔 (避免 Modbus 衝突)
                    if i < len(self.slave_ids_to_poll) - 1 and self.poll_interval_between_devices > 0:
                        # 移除冗餘的等待日誌，只執行等待
                        time.sleep(self.poll_interval_between_devices)
                
                # 輸出精簡的輪詢結果摘要 (優化後的日誌輸出)
                print(f"\n📊 輪詢結果: {' '.join(device_statuses)}") 

                # 4. 確保符合總輪詢週期
                cycle_elapsed_time = time.time() - cycle_start_time
                time_to_wait = self.total_poll_interval - cycle_elapsed_time

                if time_to_wait > 0:
                    # 修正：等待時間的日誌放在這裡，輸出總等待時間
                    print(f"\n✅ 本輪輪詢完成。等待 {time_to_wait:.2f} 秒，進入下一輪。")
                    time.sleep(time_to_wait)
                else:
                    print(f"\n⚠️ 警告：輪詢耗時 ({cycle_elapsed_time:.2f}s) 超過總週期 ({self.total_poll_interval}s)！立即開始下一輪。")
                    # 至少休息 1 秒，避免佔用過多 CPU 資源
                    time.sleep(1) 

        except KeyboardInterrupt:
            print("🛑 結束 MPPT 模組 (Keyboard Interrupt)")
        except Exception as e:
            print(f"致命錯誤：主輪詢迴圈中斷: {e}", file=sys.stderr)
        finally:
            print("清理連線中...")
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
            try:
                self.modbus_manager.close()
            except:
                pass
            print("清理完成。程式退出。")


# ========================
# 🔵 框架主進入點 (與 HA Add-on 框架兼容)
# ========================
def run(options: dict):
    """
    HA Add-on 框架會呼叫此函數。
    負責初始化配置、建立連線，並啟動 MPPTPoller 實例。
    """
    poller = None
    modbus_manager = None
    try:
        # 1. 初始化配置和 Modbus/MQTT 連線管理
        modbus_mqtt_client.initialize_config(options)
        modbus_manager = modbus_mqtt_client.get_modbus_manager()
        
        # 2. 建立並連線 MQTT 客戶端
        mqtt_client = modbus_mqtt_client.get_mqtt_client()
        # Non-blocking connect
        mqtt_client.connect(options.get('mqtt_host'), options.get('mqtt_port'), 60)
        mqtt_client.loop_start()

        # 3. 創建並啟動輪詢器
        poller = MPPTPoller(options, modbus_manager, mqtt_client)
        poller.start_polling()
        
    except Exception as e:
        print(f"❌ 模組初始化或啟動失敗: {e}", file=sys.stderr)
        # 嘗試清理連線
        if poller and hasattr(poller, 'mqtt_client'):
            try:
                poller.mqtt_client.loop_stop()
                poller.mqtt_client.disconnect()
            except:
                pass
        if modbus_manager:
            try:
                modbus_manager.close()
            except:
                pass
