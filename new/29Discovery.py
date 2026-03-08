# =============================================================================
# ha_manager.py - V2.9 真・工業封存版
# 模組名稱：Home Assistant MQTT Discovery 管理模組
# 修復 1：動態 discovery_prefix，徹底解除硬編碼
# 修復 2：引入 _get_rmap_field，完美相容 Dict (YAML) 與 Object (PY) 地圖檔
# 適用設備：MPPT 控制器、BMS、逆變器、電錶、IO 模組、RS485 傳感器
# =============================================================================

import logging
import json

logger = logging.getLogger(__name__)

class HAManager:
    """HA MQTT Discovery 管理器 V2.9 - 支援動態前綴與雙態地圖解析"""
    
    def __init__(self, mqtt_client, node_id: str, device_type: str, uid: int, rmap, discovery_prefix: str = "homeassistant"):
        self.mqtt = mqtt_client
        self.node_id = node_id
        self.device_type = device_type
        self.uid = uid
        self.rmap = rmap

        self.entity_base          = f"{node_id}_{device_type}_{uid}"
        self.base_topic           = discovery_prefix  # 動態吃參數
        self.state_topic          = f"{node_id}/{device_type}/{uid}/state"
        self.device_status_topic  = f"{node_id}/{device_type}/{uid}/status"
        self.gateway_status_topic = f"{node_id}/status"
        self.device_identifiers   = [f"{node_id}_{device_type}_addr{uid}"]

    # =========================================================================
    # 防禦層與地圖解析支援
    # =========================================================================

    def _get_rmap_field(self, field_name: str):
        """安全提取地圖欄位，相容 dict (JSON/YAML) 與 object (Class)"""
        if isinstance(self.rmap, dict):
            return self.rmap.get(field_name)
        return getattr(self.rmap, field_name, None)

    def _safe_publish(self, topic: str, payload, qos: int = 1,
                      retain: bool = False, is_json: bool = True):
        """安全發布：攔截 NaN、序列化失敗、MQTT 例外，並檢查 rc"""
        try:
            data = json.dumps(payload, allow_nan=False) if is_json else payload
            result = self.mqtt.publish(topic, data, qos=qos, retain=retain)

            if hasattr(result, "rc") and result.rc != 0:
                logger.warning(f"[{self.entity_base}] publish rc={result.rc} topic={topic}")

        except (TypeError, ValueError):
            logger.exception(f"[{self.entity_base}] JSON 序列化失敗 topic={topic} payload={payload}")
        except Exception:
            logger.exception(f"[{self.entity_base}] MQTT 發布失敗 topic={topic}")

    # =========================================================================
    # Discovery 管理
    # =========================================================================

    def send_discovery(self, cleanup: bool = False):
        op = "清除" if cleanup else "發送"
        logger.info(f"[{self.entity_base}] {op} HA Discovery V2.9...")

        # 使用安全提取方法
        b1_info = self._get_rmap_field("B1_INFO")
        if b1_info:
            for item in b1_info:
                if not isinstance(item, dict) or "ha" not in item or "key" not in item:
                    continue
                self._process_item(item, item["key"], cleanup)

        # 使用安全提取方法
        b3_bits = self._get_rmap_field("B3_STATUS_BITS")
        if b3_bits:
            for key, item in b3_bits.items():
                if not isinstance(item, dict) or "ha" not in item:
                    continue
                self._process_item({**item, "key": key}, key, cleanup)

        logger.info(f"[{self.entity_base}] Discovery {op}完成")

    def _process_item(self, item: dict, key: str, cleanup: bool):
        ha_conf = item.get("ha", {})
        if not isinstance(ha_conf, dict):
            return

        domain = ha_conf.get("type", "sensor")
        config_topic = f"{self.base_topic}/{domain}/{self.entity_base}/{key}/config"

        if cleanup:
            self._safe_publish(config_topic, "", qos=1, retain=True, is_json=False)
            return

        builder_map = {
            "sensor":        self._build_sensor_payload,
            "binary_sensor": self._build_binary_sensor_payload,
            "switch":        self._build_switch_payload,
            "number":        self._build_number_payload,
            "select":        self._build_select_payload,
            "button":        self._build_button_payload,
        }

        builder = builder_map.get(domain, self._build_sensor_payload)
        payload = builder(item, key)

        if payload is not None:
            self._safe_publish(config_topic, payload, qos=1, retain=True, is_json=True)

    # =========================================================================
    # 狀態與可用性
    # =========================================================================

    def publish_state(self, data_dict: dict):
        if not isinstance(data_dict, dict):
            return
        self._safe_publish(self.state_topic, data_dict, qos=0, retain=False, is_json=True)

    def set_availability(self, online: bool):
        self._safe_publish(self.device_status_topic,
                           "online" if online else "offline",
                           qos=1, retain=True, is_json=False)

    def publish_gateway_online(self):
        self._safe_publish(self.gateway_status_topic, "online", qos=1, retain=True, is_json=False)
        logger.info(f"📡 [{self.node_id}] 網關：online")

    def publish_gateway_offline(self):
        self._safe_publish(self.gateway_status_topic, "offline", qos=1, retain=True, is_json=False)
        logger.info(f"📡 [{self.node_id}] 網關：offline")

    # =========================================================================
    # Payload 組裝
    # =========================================================================

    def _get_base_payload(self, item: dict, key: str) -> dict:
        unique_id = f"{self.entity_base}_{key}"
        return {
            "name":           item.get("name", key),
            "unique_id":      unique_id,
            "object_id":      unique_id,
            "state_topic":    self.state_topic,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "device": {
                "identifiers": self.device_identifiers,
                "name":        f"{self.device_type.upper()} [ID:{self.uid}]",
                "model":       self.device_type.upper(),
                "manufacturer": "Edge-BusMaster",
            },
            "availability": [
                {"topic": self.gateway_status_topic, "payload_available": "online", "payload_not_available": "offline"},
                {"topic": self.device_status_topic, "payload_available": "online", "payload_not_available": "offline"},
            ],
            "availability_mode": "all",
        }

    def _apply_common(self, payload: dict, item: dict) -> dict:
        ha = item.get("ha", {})
        unit = item.get("unit")
        if unit and unit not in ("Hex", "Bit", "Enum"):
            payload["unit_of_measurement"] = unit

        for field in ("device_class", "state_class", "icon"):
            if field in ha:
                payload[field] = ha[field]
        return payload

    # =========================================================================
    # Builder
    # =========================================================================

    def _build_sensor_payload(self, item: dict, key: str) -> dict:
        return self._apply_common(self._get_base_payload(item, key), item)

    def _build_binary_sensor_payload(self, item: dict, key: str) -> dict:
        payload = self._apply_common(self._get_base_payload(item, key), item)
        payload["payload_on"]  = "ON"
        payload["payload_off"] = "OFF"
        return payload

    def _build_switch_payload(self, item: dict, key: str) -> dict:
        payload = self._apply_common(self._get_base_payload(item, key), item)
        ha = item.get("ha", {})
        payload["command_topic"]   = f"{self.node_id}/{self.device_type}/{self.uid}/set/{key}"
        payload["entity_category"] = "config"

        state_key = ha.get("state_key")
        if state_key:
            payload["value_template"] = f"{{{{ value_json.{state_key} }}}}"
            payload["state_on"]  = "ON"
            payload["state_off"] = "OFF"
        else:
            payload.pop("state_topic", None)
            payload.pop("value_template", None)
            payload["optimistic"] = True

        return payload

    def _build_number_payload(self, item: dict, key: str) -> dict:
        payload = self._apply_common(self._get_base_payload(item, key), item)
        ha = item.get("ha", {})
        payload["command_topic"]   = f"{self.node_id}/{self.device_type}/{self.uid}/set/{key}"
        payload["min"]             = ha.get("min", 0)
        payload["max"]             = ha.get("max", 100)
        payload["step"]            = ha.get("step", 1)
        payload["mode"]            = ha.get("mode", "box")
        payload["entity_category"] = "config"
        return payload

    def _build_select_payload(self, item: dict, key: str):
        ha = item.get("ha", {})
        options = ha.get("options", [])

        if not isinstance(options, list) or not options:
            logger.warning(f"[{self.entity_base}] select '{key}' options 缺失，跳過")
            return None
        if not all(isinstance(o, str) for o in options):
            logger.warning(f"[{self.entity_base}] select '{key}' options 含非字串元素，跳過")
            return None

        payload = self._apply_common(self._get_base_payload(item, key), item)
        payload["command_topic"]   = f"{self.node_id}/{self.device_type}/{self.uid}/set/{key}"
        payload["options"]         = options
        payload["entity_category"] = "config"

        link_b1 = ha.get("link_b1")
        if link_b1:
            payload["value_template"] = f"{{{{ value_json.{link_b1} }}}}"

        return payload

    def _build_button_payload(self, item: dict, key: str) -> dict:
        payload = self._get_base_payload(item, key)
        payload.pop("state_topic", None)
        payload.pop("value_template", None)

        ha = item.get("ha", {})
        payload["command_topic"] = f"{self.node_id}/{self.device_type}/{self.uid}/set/{key}"
        payload["payload_press"] = "PRESS"
        if ha.get("icon"):
            payload["icon"] = ha["icon"]
        return payload
