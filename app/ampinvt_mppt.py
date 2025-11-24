# /app/ampinvt_mppt.py
"""
📌 佛山金廣源 ampinvt MPPT RS485 通訊模組 - 多設備輪詢優化完整版

此版本功能：
- 多設備輪詢
- HA MQTT Discovery
- 自動 Modbus / MQTT 重連（在 modbus_mqtt_client.py 中）
- 啟動延遲 10 秒（在 main.py）
- 時區設定（由 options / 環境變數 TZ 控制）
- ✅ 支援「除錯模式」：可輸出 Modbus TX/RX 十六進位資訊
- ✅ 精簡 Info 日誌：每輪只輸出一行輪詢摘要

"""

import time
import json
import paho.mqtt.client as mqtt
import modbus_mqtt_client
import sys  # 用於日誌輸出
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
    "charge_power": ("瞬時充電功率", "W", "power", "measurement"),  # 這是計算出來的值
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

        # ✅ 除錯模式 flag：開啟時會輸出 Modbus TX/RX HEX
        self.debug_mode = bool(options.get('debug_mode', False))

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
    # 🛠️ Modbus 協定處理
    # ========================

    def _build_query_packet(self, address: int) -> bytes:
        """
        建立查詢封包：地址 + 0xB1 + 0x01 + [0x00,0x00,0x00,0x00] + 校驗 (共 8 bytes)
        """
        packet = bytearray([address, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
        # 計算校驗碼 (前 7 個字節相加後取最低 8 位)
        checksum = sum(packet[:7]) & 0xFF
        packet[7] = checksum
        return bytes(packet)

    def _parse_response(self, data: bytes) -> dict:
        """
        根據 PDF 協議，解析 93 bytes 回傳的所有欄位，並計算衍生值。
        """
        if len(data) != 93:
            raise ValueError(f"回應資料長度錯誤：收到 {len(data)} bytes，應為 93")

        result = {}

        # --- 💡 輔助函數 ---
        def word_to_float(high, low, scale):
            return ((high << 8) | low) / scale

        def dword_to_int(d4, d3, d2, d1):
            return (d4 << 24) | (d3 << 16) | (d2 << 8) | d1

        # ========== 1️⃣ 狀態位 (Byte 3, 4, 5) - Binary Sensor ==========
        result.update({
            "run_status": bool(data[3] & 0x01),         # 運行狀態
            "fan_status": bool(data[3] & 0x04),         # 風扇狀態
            "temp_status": bool(data[3] & 0x08),        # 溫度保護
            "int_temp1_fault": bool(data[3] & 0x20),    # 內部溫度1異常
            "charging": bool(data[4] & 0x01),           # 充電中
            "equalizing_charge": bool(data[4] & 0x02),  # 均充
            "tracking": bool(data[4] & 0x04),           # MPPT 跟蹤
            "float_charge": bool(data[4] & 0x08),       # 浮充
            "charge_limited": bool(data[4] & 0x10),     # 充電限流
            "pv_over_voltage": bool(data[4] & 0x80),    # PV 過壓
            "load_output": bool(data[5] & 0x02),        # 負載輸出
            "overcharge_protect": bool(data[5] & 0x10), # 過充保護
            "overvoltage_protect": bool(data[5] & 0x20) # 過壓保護
        })

        # ========== 2️⃣ 系統參數 & 設定值 (Sensor) ==========
        result.update({
            "battery_type": data[8],
            "battery_count": data[10],
            "rated_voltage": word_to_float(data[16], data[17], 100),
            "equalize_voltage": word_to_float(data[18], data[19], 100),
            "float_voltage": word_to_float(data[20], data[21], 100),
            "max_charge_current": word_to_float(data[26], data[27], 100),
        })

        # ========== 3️⃣ 實際測量值 (Sensor) ==========
        result.update({
            "pv_voltage": word_to_float(data[30], data[31], 10),
            "battery_voltage": word_to_float(data[32], data[33], 100),
            "charge_current": word_to_float(data[34], data[35], 100),
            "internal_temp1": word_to_float(data[36], data[37], 10),
            "external_temp1": word_to_float(data[40], data[41], 100),
        })

        # ========== 4️⃣ 發電量 (Wh) ==========
        result.update({
            "today_yield_wh": dword_to_int(data[44], data[45], data[46], data[47]),
            "total_yield_wh": dword_to_int(data[48], data[49], data[50], data[51]),
        })

        # 💡 計算瞬時充電功率 (W)
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

        # --- 1. 數值型感測器 (sensor) ---
        for key, (name, unit, device_class, _) in SENSOR_MAPPING.items():

            if key.endswith("_yield_wh"):
                state_class = "total_increasing"
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
            payload = {k: v for k, v in payload.items() if v is not None}
            self.mqtt_client.publish(topic, json.dumps(payload), retain=self.retain)

        # --- 2. 布林型感測器 (binary_sensor) ---
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
        對單一 Modbus 地址進行查詢和數據發佈，並返回狀態:
        - OK   : 成功
        - FAIL : 回應異常或資料長度錯誤
        - TOUT : 通訊逾時
        - ERR  : 其他錯誤
        """

        packet = self._build_query_packet(address)

        try:
            modbus_client = self.modbus_manager.get_client()
            sock = modbus_client.socket

            if sock is None:
                print(f"⚠️ 地址 {address}: Modbus 連線未建立或已斷開，跳過查詢。", file=sys.stderr)
                return "FAIL"

            # ✅ 除錯模式：顯示送出的 Modbus 封包 (TX)
            if self.debug_mode:
                print(f"[DEBUG] TX (addr {address}): " +
                      " ".join(f"{b:02X}" for b in packet))

            # 核心 Modbus 通訊
            sock.send(packet)
            sock.settimeout(2.0)  # 接收超時時間 (2 秒)

            response = sock.recv(93)

            # ✅ 除錯模式：顯示收到的 Modbus 回應 (RX)
            if self.debug_mode:
                print(f"[DEBUG] RX (addr {address}, len={len(response)}): " +
                      " ".join(f"{b:02X}" for b in response))

            if len(response) != 93:
                print(f"⚠️ 地址 {address} 無效回應（長度 {len(response)}），跳過發佈。", file=sys.stderr)
                return "FAIL"

            values = self._parse_response(response)

            # 發佈所有解析到的 key-value 對
            for key, value in values.items():
                if key not in SENSOR_MAPPING and key not in BINARY_SENSOR_MAPPING:
                    continue

                if isinstance(value, bool):
                    payload = "True" if value else "False"
                else:
                    payload = str(value)

                topic = f"{self.node_id}_{self.module_name}/{address}/{key}/state"
                self.mqtt_client.publish(topic, payload, retain=self.retain)

            return "OK"

        except Exception as e:
            # ✅ 一律回傳狀態，讓上層可以在摘要中看到
            if "timed out" in str(e).lower():
                status = "TOUT"
            else:
                status = "ERR"
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
                device_statuses = []  # 收集本輪的輪詢結果

                # 2. 核心輪詢迴圈
                for i, slave_id in enumerate(self.slave_ids_to_poll):

                    status = self._query_and_publish(slave_id)
                    # ✅ 即使是 TOUT / ERR 也會被記錄下來
                    device_statuses.append(f"({slave_id}:{status})")

                    # 3. 控制設備間間隔 (避免 Modbus 衝突)
                    if i < len(self.slave_ids_to_poll) - 1 and self.poll_interval_between_devices > 0:
                        time.sleep(self.poll_interval_between_devices)

                cycle_elapsed_time = time.time() - cycle_start_time
                time_to_wait = self.total_poll_interval - cycle_elapsed_time

                # ✅ 不管 debug_mode true/false 都會印這一行
                if time_to_wait > 0:
                    print(f"[INFO] 輪詢結果: {' '.join(device_statuses)} | 下一輪 {time_to_wait:.2f} 秒後")
                    time.sleep(max(time_to_wait, 0))
                else:
                    # 耗時超出週期，立即下一輪，但避免 CPU 100%
                    print(
                        f"[INFO] 輪詢結果: {' '.join(device_statuses)} | 警告：本輪耗時 {cycle_elapsed_time:.2f}s 超過設定週期 {self.total_poll_interval}s，立即開始下一輪。"
                    )
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
            except Exception:
                pass
            try:
                self.modbus_manager.close()
            except Exception:
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
            except Exception:
                pass
        if modbus_manager:
            try:
                modbus_manager.close()
            except Exception:
                pass
