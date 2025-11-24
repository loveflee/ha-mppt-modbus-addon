# /app/client/modbus_mqtt_client.py

"""
📌 Modbus 與 MQTT 連線管理模組
- 統一管理連線資訊、建立連線物件、避免重複連線
- Modbus: 取用 client 時自動檢查/重連
- MQTT: on_connect / on_disconnect 回調 + 自動重連
"""

from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt
import threading
import time
import logging

logger = logging.getLogger(__name__)

# 全局變數用於儲存從主程序傳入的配置
CONFIG = {}
_modbus_manager_instance = None


def initialize_config(options: dict):
    """
    從主程序接收 Add-on 的配置 (options.json 內容)
    """
    global CONFIG, _modbus_manager_instance
    CONFIG = options

    if _modbus_manager_instance is None:
        modbus_host = CONFIG.get('modbus_host')
        modbus_port = CONFIG.get('modbus_port')
        node_id = CONFIG.get('node_id', "ha_mppt_node")

        if modbus_host and modbus_port:
            _modbus_manager_instance = ModbusManager(
                host=modbus_host,
                port=modbus_port,
                node_id=node_id
            )
        else:
            logger.error("Modbus 連線設定不完整，請確認 modbus_host / modbus_port。")


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
        self.node_id = node_id
        self.lock = threading.Lock()
        self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=3)
        self._connect()

    def _connect(self):
        """
        嘗試連接 Modbus 伺服器
        """
        if not self.client.is_socket_open():
            if self.client.connect():
                logger.info(f"✅ Modbus NODE {self.node_id} 已連線: {self.host}:{self.port}")
                return True
            else:
                logger.warning(f"⚠️ Modbus NODE {self.node_id} 連線失敗: {self.host}:{self.port}")
                return False
        return True

    def get_client(self):
        """
        提供 Modbus client 實例（保持連線）
        - 每次取得時都檢查 socket 狀態，必要時自動重連
        """
        with self.lock:
            if not self.client.is_socket_open():
                logger.warning(f"⚠️ Modbus NODE {self.node_id} 連線中斷，嘗試重新連線...")
                self.client.close()
                self._connect()
            return self.client

    def close(self):
        """
        結束連線
        """
        with self.lock:
            try:
                self.client.close()
            except Exception:
                pass
            logger.info(f"Modbus NODE {self.node_id} 連線已關閉。")


# ==============================
# 🟣 MQTT 客戶端（共用）
# ==============================
def get_mqtt_client():
    """
    建立 MQTT 客戶端（共用設定，從 CONFIG 讀取）
    """
    mqtt_broker = CONFIG.get('mqtt_host')
    mqtt_port = CONFIG.get('mqtt_port')
    mqtt_username = CONFIG.get('mqtt_username')
    mqtt_password = CONFIG.get('mqtt_password')

    if mqtt_broker is None or mqtt_port is None:
        raise ValueError("MQTT Broker 設定不完整 (mqtt_host/mqtt_port)")

    # username/password 可以允許為空（匿名模式），所以不硬性檢查 not None
    client_id = f"{CONFIG.get('node_id', 'ha_mppt_node')}_mqtt_poller"
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    if mqtt_username is not None and mqtt_password is not None:
        client.username_pw_set(mqtt_username, mqtt_password)

    # ==========
    # 回調設定
    # ==========
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"✅ MQTT Broker 已連線: {mqtt_broker}:{mqtt_port}")
        else:
            logger.error(f"❌ MQTT Broker 連線失敗，回傳碼: {rc}")

    def on_disconnect(client, userdata, rc, properties=None):
        if rc != 0:
            logger.warning(f"⚠️ MQTT 非預期斷線 (rc={rc})，準備自動重連...")
            # 啟動一個背景執行緒做重連，避免卡住 callback thread
            def _reconnect_loop():
                backoff = 5
                while True:
                    try:
                        logger.info("嘗試重新連線 MQTT Broker...")
                        client.reconnect()
                        logger.info("MQTT 重連成功。")
                        break
                    except Exception as e:
                        logger.error(f"MQTT 重連失敗: {e}，{backoff} 秒後再試一次。")
                        time.sleep(backoff)

            t = threading.Thread(target=_reconnect_loop, daemon=True)
            t.start()
        else:
            logger.info("MQTT 正常斷線。")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # （如果未來需要 LWT，可以在這裡設定 client.will_set(...)）

    return client


# ==============================
# 🟤 單例管理器存取
# ==============================
def get_modbus_manager():
    """ 取得 ModbusManager 實例 """
    if _modbus_manager_instance is None:
        raise RuntimeError("ModbusManager 尚未初始化。請先呼叫 initialize_config(options)。")
    return _modbus_manager_instance
