# client/modbus_mqtt_client.py
"""
📌 Modbus 與 MQTT 連線管理模組
統一管理連線資訊、建立連線物件、避免重複連線
同時提供自動重連的功能
"""
from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt
import threading
import time
import sys

# 全局變數用於儲存從主程序傳入的配置
CONFIG = {}
_modbus_manager_instance = None


def initialize_config(options: dict):
    """
    從主程序接收 Add-on 的配置 (options.json 內容)
    """
    global CONFIG, _modbus_manager_instance
    CONFIG = options

    # 初始化 Modbus Manager 實例
    if _modbus_manager_instance is None:
        modbus_host = CONFIG.get('modbus_host')
        modbus_port = CONFIG.get('modbus_port')
        node_id = CONFIG.get('node_id', "ha_mppt_node")  # 提供預設值

        if modbus_host and modbus_port:
            _modbus_manager_instance = ModbusManager(
                host=modbus_host,
                port=modbus_port,
                node_id=node_id
            )
        else:
            print("❌ 錯誤: Modbus 連線設定不完整。", file=sys.stderr)


# ==============================
# 🔵 Modbus 連線管理類別（單例）
# ==============================
class ModbusManager:
    """
    用來管理單一個 Modbus TCP 連線（保持連線 & 自動重連）
    """
    def __init__(self, host, port, node_id):
        self.host = host
        self.port = port
        self.node_id = node_id  # 用於 log 輸出
        self.lock = threading.Lock()
        # timeout: 3 秒，避免堵太久
        self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=3)
        self._connect()

    def _connect(self):
        """
        嘗試連接 Modbus 伺服器
        """
        if not self.client.is_socket_open():
            if self.client.connect():
                print(f"✅ Modbus NODE {self.node_id} 已連線: {self.host}:{self.port}")
                return True
            else:
                print(f"⚠️ Modbus NODE {self.node_id} 連線失敗: {self.host}:{self.port}", file=sys.stderr)
                return False
        return True

    def get_client(self):
        """
        提供 Modbus client 實例（保持連線）
        如果連線中斷，會嘗試重新連線。
        """
        with self.lock:
            if not self.client.is_socket_open():
                print(f"⚠️ Modbus NODE {self.node_id} 連線中斷，嘗試重新連線...", file=sys.stderr)
                self.client.close()
                self._connect()

            # 即使重連失敗，也返回 client，讓上層呼叫去處理異常
            return self.client

    def close(self):
        """
        結束連線
        """
        with self.lock:
            self.client.close()


# ==============================
# 🟣 MQTT 客戶端（共用 + 自動重連）
# ==============================
def get_mqtt_client():
    """
    建立 MQTT 客戶端（共用設定，從 CONFIG 讀取）
    並加上 on_connect / on_disconnect 做基本連線診斷與重連。
    """
    mqtt_broker = CONFIG.get('mqtt_host')
    mqtt_port = CONFIG.get('mqtt_port')
    mqtt_username = CONFIG.get('mqtt_username')
    mqtt_password = CONFIG.get('mqtt_password')

    if not all([mqtt_broker, mqtt_port, mqtt_username is not None, mqtt_password is not None]):
        raise ValueError("MQTT 配置不完整，無法建立客戶端。")

    # Client ID 建議加上唯一標識
    client_id = f"{CONFIG.get('node_id', 'ha_mppt_node')}_mqtt_poller"
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    client.username_pw_set(mqtt_username, mqtt_password)

    # ✅ 連線回調：顯示成功 / 失敗
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ MQTT Broker 已連線: {mqtt_broker}:{mqtt_port}")
        else:
            print(f"❌ MQTT Broker 連線失敗，回傳碼: {rc}", file=sys.stderr)

    # ✅ 斷線回調：簡單自動重連邏輯
    def on_disconnect(client, userdata, rc):
        if rc != 0:
            print(f"⚠️ 與 MQTT Broker 非正常斷線 (rc={rc})，啟動自動重連...", file=sys.stderr)
        else:
            print("ℹ️ 已從 MQTT Broker 正常斷線。")

        # 嘗試重連（loop_start 已在外面啟動）
        while True:
            try:
                result = client.reconnect()
                if result == mqtt.MQTT_ERR_SUCCESS:
                    print("✅ MQTT 自動重連成功。")
                    break
                else:
                    print(f"⚠️ MQTT 重連失敗，回傳碼: {result}，5 秒後重試...", file=sys.stderr)
            except Exception as e:
                print(f"❌ MQTT 重連過程發生例外: {e}，5 秒後重試...", file=sys.stderr)
            time.sleep(5)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    return client


# ==============================
# 🟤 單例管理器存取
# ==============================
def get_modbus_manager():
    """ 取得 ModbusManager 實例 """
    if _modbus_manager_instance is None:
        raise RuntimeError("ModbusManager 尚未初始化。請先呼叫 initialize_config(options)。")
    return _modbus_manager_instance
