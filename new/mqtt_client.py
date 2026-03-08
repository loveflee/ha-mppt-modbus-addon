import queue
import logging
import threading
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class RobustMQTTClient:

    def __init__(self, broker: str, port: int,
                 client_id: str = "",
                 username: str = None,
                 password: str = None):

        self.broker = broker
        self.port = port

        self.msg_queue = queue.Queue(maxsize=2000)

        self.on_connected_callback = None

        self._subscriptions = set()
        self._sub_lock = threading.Lock()

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id
        )

        if username:
            self.client.username_pw_set(username, password)

        self.client.max_queued_messages_set(1000)
        self.client.max_inflight_messages_set(50)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def set_lwt(self, topic: str, payload: str = "offline", retain: bool = True):
        self.client.will_set(topic, payload, qos=1, retain=retain)

    def connect(self):

        try:

            logger.info(f"[MQTT] connect {self.broker}:{self.port}")

            self.client.connect_async(self.broker, self.port, keepalive=60)

            self.client.loop_start()

        except Exception:

            logger.exception("[MQTT] start connect failed")

    def disconnect(self):

        self.client.disconnect()

        self.client.loop_stop()

    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False):

        try:

            return self.client.publish(topic, payload, qos=qos, retain=retain)

        except Exception:

            logger.exception(f"[MQTT] publish failed topic={topic}")

            return None

    def subscribe(self, topic: str, qos: int = 0):

        with self._sub_lock:

            self._subscriptions.add((topic, qos))

        try:

            rc, _ = self.client.subscribe(topic, qos=qos)

            if rc != mqtt.MQTT_ERR_SUCCESS:

                logger.debug(f"[MQTT] subscribe rc={rc} topic={topic}")

        except Exception:

            logger.exception(f"[MQTT] subscribe error topic={topic}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):

        if reason_code == 0:

            logger.info(f"[MQTT] connected {self.broker}")

            with self._sub_lock:

                for topic, qos in self._subscriptions:

                    rc, _ = client.subscribe(topic, qos)

                    if rc != mqtt.MQTT_ERR_SUCCESS:

                        logger.debug(f"[MQTT] resub rc={rc} topic={topic}")

            if self.on_connected_callback:

                self.on_connected_callback()

        else:

            logger.error(f"[MQTT] connect refused rc={reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):

        if reason_code != 0:

            logger.warning(f"[MQTT] unexpected disconnect rc={reason_code}")

        else:

            logger.info("[MQTT] disconnected")

    def _on_message(self, client, userdata, msg):

        try:

            self.msg_queue.put_nowait(msg)

        except queue.Full:

            logger.error(f"[MQTT] queue full drop topic={msg.topic}")
