import json
from core_mqtt import RobustMQTTClient

class HAManager:
    """
    🏠 HA Manager V7.2 (Hardware Limit Support)
    """
    def __init__(self, mqtt: RobustMQTTClient, config: dict, rmap):
        self.mqtt = mqtt
        self.rmap = rmap 
        self.prefix = config['discovery_prefix']
        self.node_id = config.get('node_id', 'wifi01')
        self.dev_name = config['device_name']
        self.base_topic = f"{self.prefix}/sensor/{self.node_id}_mppt"
        self.availability_topic = f"{self.prefix}/sensor/{self.node_id}_mppt/status"
        
        self.cmd_base = {
            "switch": f"{self.prefix}/switch",
            "button": f"{self.prefix}/button",
            "number": f"{self.prefix}/number",
            "select": f"{self.prefix}/select"
        }

    def send_discovery(self, unit_ids: list, device_details: dict = {}):
        print("📤 發送 HA Discovery (V7.2 硬體限流)...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            dev_info = self._get_dev_info(uid)
            details = device_details.get(uid, {'count': 1, 'type': 0, 'hw_max': 60.0}) # 預設 60A
            
            # Sensors
            for item in self.rmap.B1_INFO:
                if "ha" in item: self._pub(uid, entity_base, item, dev_info, "sensor", "state_b1")
            for key, item in self.rmap.B3_STATUS_BITS.items():
                item['key'] = key 
                self._pub(uid, entity_base, item, dev_info, "binary_sensor", "state_bits", is_bin=True)

            # Controls
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
            "model": "Ampinvt V7.2",
            "manufacturer": "ampinvt",
        }

    def _add_availability(self, payload):
        payload["availability_topic"] = self.availability_topic
        payload["payload_available"] = "online"
        payload["payload_not_available"] = "offline"
        return payload

    def _publish_config(self, topic, payload):
        self.mqtt.publish(topic, json.dumps(self._add_availability(payload)), qos=1, retain=True)

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
        self._publish_config(topic, payload)

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
        self._publish_config(topic, payload)

    def _pub_button(self, uid, entity_base, item, dev_info):
        key = item['key']; topic = f"{self.prefix}/button/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_btn", "device": dev_info,
            "command_topic": f"{self.cmd_base['button']}/{entity_base}/{key}/set",
            "payload_press": "PRESS", "icon": item.get('icon', "mdi:gesture-tap-button")
        }
        self._publish_config(topic, payload)

    def _pub_number(self, uid, entity_base, item, dev_info, details):
        key = item['key']; ha_conf = item['ha']
        topic = f"{self.prefix}/number/{entity_base}/{key}/config"
        
        b_count = details.get('count', 1)
        b_type = details.get('type', 0)
        hw_max = details.get('hw_max', 60.0) # 🟢 取得硬體限流值
        
        # 預設範圍
        min_val = ha_conf.get('base_min', ha_conf.get('min', 0))
        max_val = ha_conf.get('base_max', ha_conf.get('max', 100))
        
        # 1. 鋰電專用範圍
        if b_type == 3 and 'li_base_min' in ha_conf:
            min_val = ha_conf['li_base_min']
            max_val = ha_conf['li_base_max']
            
        # 2. 電壓倍率計算 (僅針對有 base_min 的電壓項目)
        if 'base_min' in ha_conf:
            min_val *= b_count
            max_val *= b_count
            
        # 3. 🟢 [新增] 電流限流覆寫
        # 如果是設定電流 (set_max_charge_curr)，將上限鎖死為硬體極限
        if key == "set_max_charge_curr":
            max_val = hw_max
            # print(f"🔒 設備 {uid} 電流設定上限已鎖定為 {hw_max}A")
            
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
        self._publish_config(topic, payload)

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
        self._publish_config(topic, payload)

    def publish_state(self, uid, data, sub_topic):
        topic = f"{self.base_topic}/{uid}/{sub_topic}"
        self.mqtt.publish(topic, json.dumps(data), qos=0, retain=False)
    
    def clear_all_discovery(self, unit_ids: list):
        print("🧹 正在執行 HA 實體清除...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
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
        self.mqtt.publish(topic, "", qos=1, retain=True)
