import queue
import paho.mqtt.client as mqtt

class RobustMQTTClient:
    def __init__(self, broker: str, port: int, username: str = None, password: str = None):
        self.broker = broker
        self.port = port
        self.msg_queue = queue.Queue()
        self.on_connected_callback = None 
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username: self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def set_lwt(self, topic: str, payload: str = "offline", retain: bool = True):
        self.client.will_set(topic, payload, qos=1, retain=retain)

    def connect(self):
        try:
            print(f"📡 [MQTT] 連線至 {self.broker} ...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e: print(f"❌ [MQTT] 連線失敗: {e}")

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        try: self.client.publish(topic, payload, qos=qos, retain=retain)
        except: pass

    def subscribe(self, topic: str):
        self.client.subscribe(topic)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            if self.on_connected_callback: self.on_connected_callback()
        else: print(f"❌ [MQTT] 連線拒絕: {rc}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        if reason_code != 0: print(f"⚠️ [MQTT] 斷線 ({reason_code})")
        
    def _on_message(self, client, userdata, msg):
        self.msg_queue.put(msg)
