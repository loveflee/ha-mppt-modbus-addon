import json
from core_mqtt import RobustMQTTClient
import logging # 確保 logging 引入

logger = logging.getLogger("HA_MGR") # 確保 Logger 設置正確

class HAManager:
    """
    🏠 HA Manager V7.7 (Device Availability & Hardware Limit)
    """
    def __init__(self, mqtt: RobustMQTTClient, config: dict, rmap):
        self.mqtt = mqtt # 🟢 正確名稱是 self.mqtt
        self.rmap = rmap 
        self.prefix = config['discovery_prefix']
        self.node_id = config.get('node_id', 'wifi01')
        self.dev_name = config['device_name']
        self.base_topic = f"{self.prefix}/sensor/{self.node_id}_mppt"
        
        self.global_avail_topic = f"{self.prefix}/sensor/{self.node_id}_mppt/status"
        
        self.cmd_base = {
            "switch": f"{self.prefix}/switch",
            "button": f"{self.prefix}/button",
            "number": f"{self.prefix}/number",
            "select": f"{self.prefix}/select"
        }

    def send_discovery(self, unit_ids: list, device_details: dict = {}):
        print("📤 發送 HA Discovery (V7.7)...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            dev_info = self._get_dev_info(uid)
            details = device_details.get(uid, {'count': 1, 'type': 0, 'hw_max': 60.0})
            
            self.publish_device_availability(uid, "online")
            
            self._pub_connectivity(uid, entity_base, dev_info)
            
            for item in self.rmap.B1_INFO:
                if "ha" in item: self._pub(uid, entity_base, item, dev_info, "sensor", "state_b1")
            for key, item in self.rmap.B3_STATUS_BITS.items():
                item['key'] = key 
                self._pub(uid, entity_base, item, dev_info, "binary_sensor", "state_bits", is_bin=True)

            if hasattr(self.rmap, 'CONTROL_SWITCHES'):
                for key, item in self.rmap.CONTROL_SWITCHES.items():
                    item['key'] = key
                    self._pub_switch(uid, entity_base, item, dev_info)
            if hasattr(self.rmap, 'CONTROL_BUTTONS'):
                for key, item in self.rmap.CONTROL_BUTTONS.items():
                    item['key'] = key
                    self._pub_button(uid, entity_base, item, dev_info)
            if hasattr(self.rmap, 'D0_PARAMS'):
                for code, item in self.rmap.D0_PARAMS.items():
                    ha_type = item['ha']['type']
                    if ha_type == 'number': 
                        self._pub_number(uid, entity_base, item, dev_info, details)
                    elif ha_type == 'select': 
                        self._pub_select(uid, entity_base, item, dev_info)

    def _get_dev_info(self, uid):
        return {
            "identifiers": [f"{self.node_id}_mppt_addr{uid}"],
            "name": f"MPPT Controller #{uid}",
            "model": "Ampinvt V7.7",
            "manufacturer": "ampinvt",
        }

    def publish_connectivity_state(self, uid, is_connected: bool):
        topic = f"{self.base_topic}_{uid}/connectivity_state"
        payload = "ON" if is_connected else "OFF"
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, payload, qos=1, retain=True)

    def _pub_connectivity(self, uid, entity_base, dev_info):
        topic = f"{self.prefix}/binary_sensor/{entity_base}/connectivity/config"
        payload = {
            "name": "連線狀態",
            "unique_id": f"{entity_base}_connectivity",
            "device": dev_info,
            "state_topic": f"{self.base_topic}_{uid}/connectivity_state",
            "device_class": "connectivity", 
            "payload_on": "ON",
            "payload_off": "OFF"
        }
        payload["availability_topic"] = self.global_avail_topic
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, json.dumps(payload), qos=1, retain=True)

    def publish_device_availability(self, uid, status):
        topic = f"{self.base_topic}_{uid}/availability"
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, status, qos=1, retain=True)

    def _add_availability(self, payload, uid):
        device_avail = f"{self.base_topic}_{uid}/availability"
        payload["availability"] = [
            {"topic": self.global_avail_topic},
            {"topic": device_avail}
        ]
        payload["payload_available"] = "online"
        payload["payload_not_available"] = "offline"
        return payload

    def _publish_config(self, topic, payload):
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, json.dumps(payload), qos=1, retain=True)

    def _pub(self, uid, entity_base, item, dev_info, domain, sub_topic, is_bin=False):
        key = item['key']
        unique_id = f"{entity_base}_{key}" + ("_bs" if is_bin else "")
        topic = f"{self.prefix}/{domain}/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": unique_id, "device": dev_info,
            "state_topic": f"{self.base_topic}/{uid}/{sub_topic}",
            "value_template": f"{{{{ value_json.{key} }}}}",
        }
        if not is_bin and item.get('unit'): payload["unit_of_measurement"] = item['unit']
        if item['ha'].get('icon'): payload["icon"] = item['ha']['icon']
        if item['ha'].get('device_class'): payload["device_class"] = item['ha']['device_class']
        if item['ha'].get('state_class'): payload["state_class"] = item['ha']['state_class']
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_switch(self, uid, entity_base, item, dev_info):
        key = item['key']; topic = f"{self.prefix}/switch/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_sw", "device": dev_info,
            "command_topic": f"{self.cmd_base['switch']}/{entity_base}/{key}/set",
            "icon": item.get('icon', "mdi:toggle-switch")
        }
        if item.get('state_key'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_bits"
            payload["value_template"] = f"{{{{ value_json.{item['state_key']} }}}}"
        else: payload["optimistic"] = True
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_button(self, uid, entity_base, item, dev_info):
        key = item['key']; topic = f"{self.prefix}/button/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_btn", "device": dev_info,
            "command_topic": f"{self.cmd_base['button']}/{entity_base}/{key}/set",
            "payload_press": "PRESS", "icon": item.get('icon', "mdi:gesture-tap-button")
        }
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_number(self, uid, entity_base, item, dev_info, details):
        key = item['key']; ha_conf = item['ha']
        topic = f"{self.prefix}/number/{entity_base}/{key}/config"
        b_count = details.get('count', 1); b_type = details.get('type', 0); hw_max = details.get('hw_max', 60.0)
        
        min_val = ha_conf.get('base_min', ha_conf.get('min', 0))
        max_val = ha_conf.get('base_max', ha_conf.get('max', 100))
        if b_type == 3 and 'li_base_min' in ha_conf: min_val = ha_conf['li_base_min']; max_val = ha_conf['li_base_max']
        if 'base_min' in ha_conf: min_val *= b_count; max_val *= b_count
        if key == "set_max_charge_curr": max_val = hw_max
            
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_num", "device": dev_info,
            "command_topic": f"{self.cmd_base['number']}/{entity_base}/{key}/set",
            "min": min_val, "max": max_val, "step": ha_conf.get('step', 0.1),
            "mode": ha_conf.get('mode', 'box'), "icon": ha_conf.get('icon', "mdi:dialpad")
        }
        if item.get('unit'): payload["unit_of_measurement"] = item['unit']
        if ha_conf.get('link_b1'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{ha_conf['link_b1']} }}}}"
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_select(self, uid, entity_base, item, dev_info):
        key = item['key']; ha_conf = item['ha']
        topic = f"{self.prefix}/select/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_sel", "device": dev_info,
            "command_topic": f"{self.cmd_base['select']}/{entity_base}/{key}/set",
            "options": ha_conf.get('options', []), "icon": ha_conf.get('icon', "mdi:format-list-bulleted")
        }
        if ha_conf.get('link_b1'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{ha_conf['link_b1']} }}}}"
        self._publish_config(topic, self._add_availability(payload, uid))

    def publish_state(self, uid, data, sub_topic):
        topic = f"{self.base_topic}/{uid}/{sub_topic}"
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, json.dumps(data), qos=0, retain=False)
    
    def clear_all_discovery(self, unit_ids: list):
        print("🧹 正在執行 HA 實體清除...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            self._clear(entity_base, "connectivity", "binary_sensor") 
            for item in self.rmap.B1_INFO:
                if "ha" in item: self._clear(entity_base, item['key'], "sensor")
            for key in self.rmap.B3_STATUS_BITS.keys():
                self._clear(entity_base, key, "binary_sensor")
            if hasattr(self.rmap, 'CONTROL_SWITCHES'):
                for key in self.rmap.CONTROL_SWITCHES.keys(): self._clear(entity_base, key, "switch")
            if hasattr(self.rmap, 'CONTROL_BUTTONS'):
                for key in self.rmap.CONTROL_BUTTONS.keys(): self._clear(entity_base, key, "button")
            if hasattr(self.rmap, 'D0_PARAMS'):
                for code, item in self.rmap.D0_PARAMS.items():
                    ha_type = item['ha']['type']
                    self._clear(entity_base, item['key'], ha_type)

    def _clear(self, entity_base, key, domain):
        topic = f"{self.prefix}/{domain}/{entity_base}/{key}/config"
        # 🟢 [修正] 使用 self.mqtt
        self.mqtt.publish(topic, "", qos=1, retain=True)
