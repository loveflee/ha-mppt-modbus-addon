import json
from core_mqtt import RobustMQTTClient
import mppt_register_map as rmap

class HAManager:
    """
    🏠 HA Manager V3.0: 支援 Sensor, Binary, Switch, Button, Number, Select
    """
    def __init__(self, mqtt: RobustMQTTClient, config: dict):
        self.mqtt = mqtt
        self.prefix = config['discovery_prefix']
        self.node_id = config.get('node_id', 'wifi01')
        self.dev_name = config['device_name']
        self.base_topic = f"{self.prefix}/sensor/{self.node_id}_mppt"
        
        # Command Topics
        self.cmd_base = {
            "switch": f"{self.prefix}/switch",
            "button": f"{self.prefix}/button",
            "number": f"{self.prefix}/number",
            "select": f"{self.prefix}/select"
        }

    def send_discovery(self, unit_ids: list):
        print("📤 發送 HA Discovery (全功能版)...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            dev_info = self._get_dev_info(uid)
            
            # 1. Sensors & Binary
            for item in rmap.B1_INFO:
                if "ha" in item: self._pub(uid, entity_base, item, dev_info, "sensor", "state_b1")
            for key, item in rmap.B3_STATUS_BITS.items():
                item['key'] = key 
                self._pub(uid, entity_base, item, dev_info, "binary_sensor", "state_bits", is_bin=True)

            # 2. Controls (Switch, Button)
            if hasattr(rmap, 'CONTROL_SWITCHES'):
                for key, item in rmap.CONTROL_SWITCHES.items():
                    item['key'] = key
                    self._pub_switch(uid, entity_base, item, dev_info)
            if hasattr(rmap, 'CONTROL_BUTTONS'):
                for key, item in rmap.CONTROL_BUTTONS.items():
                    item['key'] = key
                    self._pub_button(uid, entity_base, item, dev_info)

            # 3. 🟢 Settings (Number, Select) from D0_PARAMS
            if hasattr(rmap, 'D0_PARAMS'):
                for code, item in rmap.D0_PARAMS.items():
                    ha_type = item['ha']['type']
                    if ha_type == 'number':
                        self._pub_number(uid, entity_base, item, dev_info)
                    elif ha_type == 'select':
                        self._pub_select(uid, entity_base, item, dev_info)

    def _get_dev_info(self, uid):
        return {
            "identifiers": [f"{self.node_id}_mppt_addr{uid}"],
            "name": f"MPPT 控制器 #{uid}",
            "model": "Ampinvt V3.0 (RW)",
            "manufacturer": "ampinvt",
        }

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
        self.mqtt.publish(topic, json.dumps(payload), retain=True)

    def _pub_switch(self, uid, entity_base, item, dev_info):
        key = item['key']
        topic = f"{self.prefix}/switch/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_sw", "device": dev_info,
            "command_topic": f"{self.cmd_base['switch']}/{entity_base}/{key}/set",
            "icon": item.get('icon', "mdi:toggle-switch")
        }
        if item.get('state_key'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_bits"
            payload["value_template"] = f"{{{{ value_json.{item['state_key']} }}}}"
        else: payload["optimistic"] = True
        self.mqtt.publish(topic, json.dumps(payload), retain=True)

    def _pub_button(self, uid, entity_base, item, dev_info):
        key = item['key']
        topic = f"{self.prefix}/button/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_btn", "device": dev_info,
            "command_topic": f"{self.cmd_base['button']}/{entity_base}/{key}/set",
            "payload_press": "PRESS", "icon": item.get('icon', "mdi:gesture-tap-button")
        }
        self.mqtt.publish(topic, json.dumps(payload), retain=True)

    def _pub_number(self, uid, entity_base, item, dev_info):
        """🟢 註冊 Number 實體 (電壓/電流設定)"""
        key = item['key']
        ha_conf = item['ha']
        topic = f"{self.prefix}/number/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_num", "device": dev_info,
            "command_topic": f"{self.cmd_base['number']}/{entity_base}/{key}/set",
            "min": ha_conf.get('min', 0), "max": ha_conf.get('max', 100), "step": ha_conf.get('step', 0.1),
            "mode": ha_conf.get('mode', 'box'), "icon": ha_conf.get('icon', "mdi:dialpad")
        }
        if item.get('unit'): payload["unit_of_measurement"] = item['unit']
        
        # 綁定 B1 讀取值作為狀態
        if ha_conf.get('link_b1'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{ha_conf['link_b1']} }}}}"
            
        self.mqtt.publish(topic, json.dumps(payload), retain=True)

    def _pub_select(self, uid, entity_base, item, dev_info):
        """🟢 註冊 Select 實體 (下拉選單)"""
        key = item['key']
        ha_conf = item['ha']
        topic = f"{self.prefix}/select/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], "unique_id": f"{entity_base}_{key}_sel", "device": dev_info,
            "command_topic": f"{self.cmd_base['select']}/{entity_base}/{key}/set",
            "options": ha_conf.get('options', []), "icon": ha_conf.get('icon', "mdi:format-list-bulleted")
        }
        
        if ha_conf.get('link_b1'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{ha_conf['link_b1']} }}}}"
            
        self.mqtt.publish(topic, json.dumps(payload), retain=True)

    def publish_state(self, uid, data, sub_topic):
        topic = f"{self.base_topic}/{uid}/{sub_topic}"
        self.mqtt.publish(topic, json.dumps(data))
    
    # ... clear 方法與之前相同，可保留 ...
    def clear_all_discovery(self, unit_ids: list):
        print("🧹 正在執行 HA 實體清除...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            # Clear logic... (略，維持原樣即可)
