# =============================================================================
# ha_manager.py - V2.8 工業封存版
# 模組名稱：Home Assistant MQTT Discovery 管理模組
# 修復：類別縮排錯誤、__name__ 語法、publish rc 檢查、options 元素型別驗證
# 適用設備：MPPT 控制器、BMS、逆變器、電錶、IO 模組、RS485 傳感器
# =============================================================================

import logging
import json

# 修正：必須使用 Python 內建模組變數 __name__
logger = logging.getLogger(__name__)

class HAManager:
    """HA MQTT Discovery 管理器 V2.8 - 全資料驅動、設備解耦、防禦性編程滿配"""
    def __init__(self, mqtt_client, node_id: str, device_type: str, uid: int, rmap, discovery_prefix: str = "homeassistant"):
#    def __init__(self, mqtt_client, node_id: str, device_type: str, uid: int, rmap):
        self.mqtt = mqtt_client
        self.node_id = node_id
        self.device_type = device_type
        self.uid = uid
        self.rmap = rmap

        self.entity_base         = f"{node_id}_{device_type}_{uid}"
#        self.base_topic          = "homeassistant"
        # 改成動態吃參數
        self.base_topic           = discovery_prefix
        self.state_topic         = f"{node_id}/{device_type}/{uid}/state"
        self.device_status_topic = f"{node_id}/{device_type}/{uid}/status"
        self.gateway_status_topic = f"{node_id}/status"
        self.device_identifiers  = [f"{node_id}_{device_type}_addr{uid}"]

    # =========================================================================
    # 防禦層
    # =========================================================================

    def _safe_publish(self, topic: str, payload, qos: int = 1,
                      retain: bool = False, is_json: bool = True):
        """安全發布：攔截 NaN、序列化失敗、MQTT 例外，並檢查 rc"""
        try:
            data = json.dumps(payload, allow_nan=False) if is_json else payload
            result = self.mqtt.publish(topic, data, qos=qos, retain=retain)

            # 檢查 paho publish rc（rc != 0 表示 broker 拒絕或本地佇列滿）
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
        """發布或清除所有實體 Discovery。cleanup=True 請先於 send_discovery() 呼叫"""
        op = "清除" if cleanup else "發送"
        logger.info(f"[{self.entity_base}] {op} HA Discovery V2.8...")

        # B1_INFO：list 格式
        if hasattr(self.rmap, "B1_INFO"):
            for item in self.rmap.B1_INFO:
                if not isinstance(item, dict) or "ha" not in item or "key" not in item:
                    continue
                self._process_item(item, item["key"], cleanup)

        # B3_STATUS_BITS：dict 格式，必須用 .items() 迭代
        if hasattr(self.rmap, "B3_STATUS_BITS"):
            for key, item in self.rmap.B3_STATUS_BITS.items():
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
        """發布狀態數據（qos=0, retain=False）。NaN 值會被攔截記錄"""
        if not isinstance(data_dict, dict):
            return
        self._safe_publish(self.state_topic, data_dict, qos=0, retain=False, is_json=True)

    def set_availability(self, online: bool):
        """發布設備可用性：輪詢成功=online，連續失敗=offline"""
        self._safe_publish(self.device_status_topic,
                           "online" if online else "offline",
                           qos=1, retain=True, is_json=False)

    def publish_gateway_online(self):
        """網關上線，應在 on_connected callback 中呼叫"""
        self._safe_publish(self.gateway_status_topic, "online", qos=1, retain=True, is_json=False)
        logger.info(f"📡 [{self.node_id}] 網關：online")

    def publish_gateway_offline(self):
        """網關離線，應在 SIGTERM handler 中呼叫；崩潰時由 LWT 自動處理"""
        self._safe_publish(self.gateway_status_topic, "offline", qos=1, retain=True, is_json=False)
        logger.info(f"📡 [{self.node_id}] 網關：offline")

    # =========================================================================
    # Payload 組裝
    # =========================================================================

    def _get_base_payload(self, item: dict, key: str) -> dict:
        """所有實體共用基礎 payload（雙重 AND 可用性）"""
        unique_id = f"{self.entity_base}_{key}"
        return {
            "name":           item.get("name", key),
            "unique_id":      unique_id,
            "object_id":      unique_id,   # 強制 entity_id，避免中文產生拼音
            "state_topic":    self.state_topic,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "device": {
                "identifiers": self.device_identifiers,
                "name":        f"{self.device_type.upper()} [ID:{self.uid}]",
                "model":       self.device_type.upper(),
                "manufacturer": "Edge-BusMaster",
            },
            "availability": [
                {"topic": self.gateway_status_topic,
                 "payload_available": "online", "payload_not_available": "offline"},
                {"topic": self.device_status_topic,
                 "payload_available": "online", "payload_not_available": "offline"},
            ],
            "availability_mode": "all",
        }

    def _apply_common(self, payload: dict, item: dict) -> dict:
        """套用 unit / device_class / state_class / icon"""
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
            # 注意：state_key 的數據必須包含在 publish_state() 發布的同一個 JSON 內
            # 若 switch 狀態來自不同 topic（如 state_bits），需在呼叫端合併後一起發布
            payload["value_template"] = f"{{{{ value_json.{state_key} }}}}"
            payload["state_on"]  = "ON"
            payload["state_off"] = "OFF"
        else:
            # 無狀態回讀：樂觀模式，UI 立即反映，防止開關回彈
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
        payload["mode"]            = ha.get("mode", "box")  # box=文字輸入，slider=滑桿
        payload["entity_category"] = "config"
        return payload

    def _build_select_payload(self, item: dict, key: str):
        ha = item.get("ha", {})
        options = ha.get("options", [])

        # 嚴格校驗：必須是非空的純字串 list，否則 HA select 建立失敗
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
        payload.pop("state_topic", None)    # button 無狀態
        payload.pop("value_template", None)

        ha = item.get("ha", {})
        payload["command_topic"] = f"{self.node_id}/{self.device_type}/{self.uid}/set/{key}"
        payload["payload_press"] = "PRESS"
        if ha.get("icon"):
            payload["icon"] = ha["icon"]
        return payload
