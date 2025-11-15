"""
📌 佛山金廣源 MPPT RS485 通訊模組 - 多設備輪詢優化完整版 (0xB1 指令 93 bytes)
說明：
此版本重構成 Python 類別 (MPPTPoller)，移除了所有全局變數，提升代碼維護性。
支援多台 MPPT 設備輪詢，並嚴格控制設備間隔和總輪詢週期。
HA Discovery 會為每個 Slave ID 創建一個獨立的 Home Assistant 裝置。
"""

import time
import json
import paho.mqtt.client as mqtt
import modbus_mqtt_client
import sys # 用於日誌輸出

# ========================
# ⚙️ 參數設定與感測器集中映射表 (常量)
# ========================

# 數值型感測器定義 (Key: (名稱, 單位, device_class, state_class))
SENSOR_MAPPING = {
    # 核心監控數據
    "pv_voltage": ("PV 電壓", "V", "voltage", "measurement"),
    "battery_voltage": ("電池電壓", "V", "voltage", "measurement"),
    "charge_current": ("充電電流", "A", "current", "measurement"),
    "charge_power": ("瞬時充電功率", "W", "power", "measurement"),
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
    "tracking": ("MPPT 追蹤中", "running"),
    "pv_over_voltage": ("PV 過壓警告", "problem"),
    "overcharge_protect": ("過充保護啟用", "problem"),
}

# ========================
# 📦 MPPTPoller 類別 (核心邏輯)
# ========================
class MPPTPoller:

    def __init__(self, options: dict, modbus_manager, mqtt_client):
        """
        初始化 MPPTPoller 實例，儲存所有配置和客戶端。
        """
        # 配置屬性 (取代全局變數)
        self.node_id = options.get('node_id')
        self.module_name = options.get('module_name')
        self.retain = options.get('mqtt_retain', False)
        self.total_poll_interval = options.get('poll_interval_seconds', 20)
        device_delay_ms = options.get('device_delay_ms', 500)
        self.poll_interval_between_devices = device_delay_ms / 1000.0

        # 連線實例
        self.modbus_manager = modbus_manager
        self.mqtt_client = mqtt_client

        # 解析 Slave IDs
        slave_ids_str = options.get('slave_ids', '')
        try:
            self.slave_ids_to_poll = [int(i.strip()) for i in slave_ids_str.split(',') if i.strip()]
        except ValueError:
            print("🛑 錯誤：無法解析 slave_ids，請檢查格式是否為 '1,2,3'", file=sys.stderr)
            self.slave_ids_to_poll = []

        if not self.slave_ids_to_poll:
            print("🛑 錯誤：SLAVE_IDS_TO_POLL 列表為空，請配置要讀取的地址。", file=sys.stderr)

        self.device_info_base = {
            "model": "MPPT RS485 (優化輪詢版)",
            "manufacturer": "佛山金广源"
        }

    # ========================
    # 🛠️ Modbus 協定處理 (佔位符)
    # ========================

    def _build_query_packet(self, address: int) -> bytes:
        """
        [佔位符] 構建發送給 MPPT 設備的 0xB1 指令封包 (共 6 bytes)
        格式：SlaveID(1B) + CMD(1B=0xB1) + 起始位址(2B=0x0000) + 數據長度(2B=0x005D=93)
        注意：實際協議可能需要 CRC 或 Checksum，此處僅為結構佔位。
        """
        # 假設您的協議是：地址, 功能碼, 起始位址(2B), 數據長度(2B), CRC(2B)
        # 由於是 0xB1 指令，我們假設它是一個自定義的查詢。
        
        # 構建一個模擬的 6-byte 查詢，實際中需替換為正確的協議封包
        packet_data = bytes([address, 0xB1, 0x00, 0x00, 0x00, 0x5D])
        # 如果需要 CRC，請在這裡計算並加入
        # crc = self._calculate_crc16(packet_data)
        # return packet_data + crc
        return packet_data

    def _parse_response(self, response: bytes) -> dict:
        """
        [佔位符] 解析來自 MPPT 設備的 93 bytes 回應。
        """
        values = {}
        # 假設:
        # PV 電壓 (PV_Voltage, bytes 4-5) - 單位 0.01V
        values['pv_voltage'] = (response[3] * 256 + response[4]) / 100.0
        # 電池電壓 (Battery_Voltage, bytes 6-7) - 單位 0.01V
        values['battery_voltage'] = (response[5] * 256 + response[6]) / 100.0
        # 瞬時充電功率 (Charge_Power, bytes 12-13) - 單位 1W
        values['charge_power'] = (response[11] * 256 + response[12])
        # 總發電量 (Total_Yield_Wh, bytes 90-91) - 單位 10Wh
        values['total_yield_wh'] = (response[89] * 256 + response[90]) * 10
        # 運行狀態 (Run Status, byte 2)
        values['run_status'] = (response[1] & 0x01) > 0  # 假設狀態位在某個位元上

        # 警告：實際應用中，請用您設備的正確地址和解析邏輯替換此處
        return values

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
        for key, (name, unit, device_class, state_class) in SENSOR_MAPPING.items():
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

    def _query_and_publish(self, address: int):
        """ 對單一 Modbus 地址進行查詢和數據發佈 """
        
        packet = self._build_query_packet(address)

        try:
            modbus_client = self.modbus_manager.get_client()
            # 警告：直接存取 .socket 依賴於底層客戶端實現 (如 pymodbus)
            sock = modbus_client.socket 
            
            if sock is None:
                 print(f"⚠️ 地址 {address}: Modbus 連線未建立或已斷開，跳過查詢。")
                 return

            sock.send(packet)
            sock.settimeout(3.0) # 設置接收超時時間
            response = sock.recv(93)

            if len(response) != 93:
                print(f"⚠️ 地址 {address} 無效回應（長度 {len(response)}），跳過發佈。")
                return
            
            # TODO: 實際應用中，請在此處加入 Checksum/CRC 驗證

            values = self._parse_response(response)

            # 🚀 循環發佈所有解析到的 key-value 對
            for key, value in values.items():
                if key not in SENSOR_MAPPING and key not in BINARY_SENSOR_MAPPING:
                    # 跳過未在映射表中定義的 key (安全機制)
                    continue 

                if isinstance(value, bool):
                    payload = "True" if value else "False"
                else:
                    payload = str(value)
                
                # 數據發佈 Topic 必須包含地址
                topic = f"{self.node_id}_{self.module_name}/{address}/{key}/state"
                self.mqtt_client.publish(topic, payload, retain=self.retain)

            print(f"✅ 地址 {address} 數據發佈完成。")

        except Exception as e:
            print(f"❌ 查詢地址 {address} 發生錯誤: {e}", file=sys.stderr)
            # 考慮在這裡嘗試重連 Modbus 或紀錄錯誤，避免連線永久中斷

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

                # 2. 核心輪詢迴圈
                for i, slave_id in enumerate(self.slave_ids_to_poll):
                    print(f"\n--- 開始讀取設備 {i+1}/{len(self.slave_ids_to_poll)} (地址 {slave_id}) ---")

                    self._query_and_publish(slave_id)

                    # 3. 控制設備間間隔 (避免 Modbus 衝突)
                    if i < len(self.slave_ids_to_poll) - 1 and self.poll_interval_between_devices > 0:
                        print(f"等待 {self.poll_interval_between_devices:.2f} 秒後讀取下一台...")
                        time.sleep(self.poll_interval_between_devices)

                # 4. 確保符合總輪詢週期
                cycle_elapsed_time = time.time() - cycle_start_time
                time_to_wait = self.total_poll_interval - cycle_elapsed_time

                if time_to_wait > 0:
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
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.modbus_manager.close()


# ========================
# 🔵 框架主進入點 (與 HA Add-on 框架兼容)
# ========================
def run(options: dict):
    """
    HA Add-on 框架會呼叫此函數。
    負責初始化配置、建立連線，並啟動 MPPTPoller 實例。
    """
    try:
        # 1. 初始化配置
        modbus_mqtt_client.initialize_config(options)
        modbus_manager = modbus_mqtt_client.get_modbus_manager()
        
        # 2. 建立並連線 MQTT 客戶端
        mqtt_client = modbus_mqtt_client.get_mqtt_client()
        mqtt_client.connect(options.get('mqtt_host'), options.get('mqtt_port'), 60)
        mqtt_client.loop_start()

        # 3. 創建並啟動輪詢器
        poller = MPPTPoller(options, modbus_manager, mqtt_client)
        poller.start_polling()
        
    except Exception as e:
        print(f"❌ 模組初始化或啟動失敗: {e}", file=sys.stderr)
        if 'poller' in locals() and hasattr(poller, 'mqtt_client'):
             # 嘗試清理連線
            poller.mqtt_client.loop_stop()
            poller.mqtt_client.disconnect()
            modbus_manager.close()
