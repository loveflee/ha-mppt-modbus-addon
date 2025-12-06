import queue
import paho.mqtt.client as mqtt
from typing import Callable, Optional

class RobustMQTTClient:
    """
    🛡️ 工業級 MQTT 連線核心 (V2.1 Protocol Fix)
    修復 Paho MQTT V2.0 回調參數不匹配的問題
    """
    def __init__(self, broker: str, port: int, username: str = None, password: str = None):
        self.broker = broker
        self.port = port
        self.msg_queue = queue.Queue()
        self.on_connected_callback: Optional[Callable] = None 

        # 使用 VERSION2 API
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        if username:
            self.client.username_pw_set(username, password)
            
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def set_lwt(self, topic: str, payload: str = "offline", retain: bool = True):
        self.client.will_set(topic, payload, retain=retain)

    def connect(self):
        try:
            print(f"📡 [MQTT] 連線至 {self.broker} ...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ [MQTT] 連線失敗: {e}")

    def publish(self, topic: str, payload: str, retain: bool = False):
        self.client.publish(topic, payload, retain=retain)

    def subscribe(self, topic: str):
        self.client.subscribe(topic)

    # 🛠️ [修復] 增加 properties 參數以相容 Paho V2
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("✅ [MQTT] 已連線")
            if self.on_connected_callback:
                self.on_connected_callback()
        else:
            print(f"❌ [MQTT] 連線拒絕: {rc}")

    # 🛠️ [修復] 增加 disconnect_flags 和 properties 參數以相容 Paho V2
    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        if reason_code != 0: 
            print("⚠️ [MQTT] 斷線，嘗試重連...")

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            self.msg_queue.put({"topic": msg.topic, "payload": payload})
        except: pass
