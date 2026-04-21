# -*- coding: utf-8 -*-
import json
from core_mqtt import RobustMQTTClient
import logging

logger = logging.getLogger("HA_MGR")

class HAManager:
    """
    🏠 HA Manager V8.1 (UTF-8 Fix, Text Entity & Indent Corrected)
    🔥 修正：嚴格對齊所有 class 內部方法的縮排，解決 AttributeError。
    🔥 升級：完整支援 text 實體 (時控輸入) 與狀態回饋閉環。
    """
    def __init__(self, mqtt: RobustMQTTClient, config: dict, rmap):
        self.mqtt = mqtt
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
            "select": f"{self.prefix}/select",
            "text": f"{self.prefix}/text"  # 🔥 補上 text 的命令路徑
        }

    def _dumps(self, payload: dict) -> str:
        """ 強制 UTF-8 輸出，解決 HA 實體變成拼音的底層問題 """
        return json.dumps(payload, ensure_ascii=False)

    def send_discovery(self, unit_ids: list, device_details: dict = {}):
        logger.info("📤 發送 HA Discovery (V8.1)...")
        for uid in unit_ids:
            entity_base = f"{self.node_id}_mppt_{uid}"
            dev_info = self._get_dev_info(uid)
            details = device_details.get(uid, {'count': 1, 'type': 0, 'hw_max': 60.0})
            
            self.publish_device_availability(uid, "online")
            self._pub_connectivity(uid, entity_base, dev_info)
            
            for item in self.rmap.B1_INFO:
                if "ha" in item: 
                    self._pub(uid, entity_base, item, dev_info, "sensor", "state_b1")
            
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
                    elif ha_type == 'text':  
                        self._pub_text(uid, entity_base, item, dev_info) # 🔥 呼叫 Text 發佈

    def _get_dev_info(self, uid):
        return {
            "identifiers": [f"{self.node_id}_mppt_addr{uid}"],
            "name": f"MPPT Controller #{uid}",
            "model": "Ampinvt V8.1",
            "manufacturer": "ampinvt",
        }

    def publish_connectivity_state(self, uid, is_connected: bool):
        topic = f"{self.base_topic}_{uid}/connectivity_state"
        payload = "ON" if is_connected else "OFF"
        self.mqtt.publish(topic, payload, qos=1, retain=True)

    def _add_availability(self, payload, uid):
        device_avail = f"{self.base_topic}_{uid}/availability"
        payload["availability"] = [
            {"topic": self.global_avail_topic, "payload_available": "online", "payload_not_available": "offline"},
            {"topic": device_avail, "payload_available": "online", "payload_not_available": "offline"}
        ]
        payload["availability_mode"] = "all"
        return payload

    def _publish_config(self, topic, payload):
        """ 統一的發佈出口，確保全部走 _dumps (UTF-8) """
        self.mqtt.publish(topic, self._dumps(payload), qos=1, retain=True)

    def _pub_connectivity(self, uid, entity_base, dev_info):
        topic = f"{self.prefix}/binary_sensor/{entity_base}/connectivity/config"
        unique_id = f"{entity_base}_connectivity"
        payload = {
            "name": "連線狀態",
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
            "state_topic": f"{self.base_topic}_{uid}/connectivity_state",
            "device_class": "connectivity", 
            "payload_on": "ON",
            "payload_off": "OFF"
        }
        self._publish_config(topic, self._add_availability(payload, uid))

    def publish_device_availability(self, uid, status):
        topic = f"{self.base_topic}_{uid}/availability"
        self.mqtt.publish(topic, status, qos=1, retain=True)

    def _pub(self, uid, entity_base, item, dev_info, domain, sub_topic, is_bin=False):
        key = item['key']
        unique_id = f"{entity_base}_{key}" + ("_bs" if is_bin else "")
        topic = f"{self.prefix}/{domain}/{entity_base}/{key}/config"
        payload = {
            "name": item['name'], 
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
            "state_topic": f"{self.base_topic}/{uid}/{sub_topic}",
            "value_template": f"{{{{ value_json.{key} }}}}",
        }
        if not is_bin and item.get('unit'): payload["unit_of_measurement"] = item['unit']
        if item['ha'].get('icon'): payload["icon"] = item['ha']['icon']
        if item['ha'].get('device_class'): payload["device_class"] = item['ha']['device_class']
        if item['ha'].get('state_class'): payload["state_class"] = item['ha']['state_class']
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_switch(self, uid, entity_base, item, dev_info):
        key = item['key']
        topic = f"{self.prefix}/switch/{entity_base}/{key}/config"
        unique_id = f"{entity_base}_{key}_sw"
        payload = {
            "name": item['name'], 
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
            "command_topic": f"{self.cmd_base['switch']}/{entity_base}/{key}/set",
            "icon": item.get('icon', "mdi:toggle-switch")
        }
        if item.get('state_key'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_bits"
            payload["value_template"] = f"{{{{ value_json.{item['state_key']} }}}}"
        else: payload["optimistic"] = True
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_button(self, uid, entity_base, item, dev_info):
        key = item['key']
        topic = f"{self.prefix}/button/{entity_base}/{key}/config"
        unique_id = f"{entity_base}_{key}_btn"
        payload = {
            "name": item['name'], 
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
            "command_topic": f"{self.cmd_base['button']}/{entity_base}/{key}/set",
            "payload_press": "PRESS", 
            "icon": item.get('icon', "mdi:gesture-tap-button")
        }
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_number(self, uid, entity_base, item, dev_info, details):
        key = item['key']
        ha_conf = item['ha']
        topic = f"{self.prefix}/number/{entity_base}/{key}/config"
        b_count = details.get('count', 1)
        b_type = details.get('type', 0)
        hw_max = details.get('hw_max', 60.0)
        
        min_val = ha_conf.get('base_min', ha_conf.get('min', 0))
        max_val = ha_conf.get('base_max', ha_conf.get('max', 100))
        if b_type == 3 and 'li_base_min' in ha_conf: 
            min_val = ha_conf['li_base_min']
            max_val = ha_conf['li_base_max']
        if 'base_min' in ha_conf: 
            min_val *= b_count
            max_val *= b_count
        if key == "set_max_charge_curr": max_val = hw_max
            
        unique_id = f"{entity_base}_{key}_num"
        payload = {
            "name": item['name'], 
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
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
        key = item['key']
        ha_conf = item['ha']
        topic = f"{self.prefix}/select/{entity_base}/{key}/config"
        unique_id = f"{entity_base}_{key}_sel"
        payload = {
            "name": item['name'], 
            "unique_id": unique_id,
            "object_id": unique_id, 
            "device": dev_info,
            "command_topic": f"{self.cmd_base['select']}/{entity_base}/{key}/set",
            "options": ha_conf.get('options', []), 
            "icon": ha_conf.get('icon', "mdi:format-list-bulleted")
        }
        if ha_conf.get('link_b1'):
            payload["state_topic"] = f"{self.base_topic}/{uid}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{ha_conf['link_b1']} }}}}"
        self._publish_config(topic, self._add_availability(payload, uid))

    def _pub_text(self, uid, entity_base, item, dev_info):
        """ 🔥 確保這個函數嚴格縮排在 class 內部，負責時控的字串下發 """
        key = item['key']
        ha_conf = item['ha']
        topic = f"{self.prefix}/text/{entity_base}/{key}/config"
        unique_id = f"{entity_base}_{key}_txt"
        payload = {
            "name": item['name'],
            "unique_id": unique_id,
            "object_id": unique_id,
            "device": dev_info,
            "command_topic": f"{self.cmd_base['text']}/{entity_base}/{key}/set",
            "state_topic": f"{self.base_topic}/{uid}/state_b1", # 接收設備當前時間
            "value_template": f"{{{{ value_json.{key} }}}}",
            "icon": ha_conf.get('icon', "mdi:form-textbox"),
            "pattern": ha_conf.get('pattern') # 啟用 HA 前端防呆正則
        }
        self._publish_config(topic, self._add_availability(payload, uid))

    def publish_state(self, uid, data, sub_topic):
        topic = f"{self.base_topic}/{uid}/{sub_topic}"
        self.mqtt.publish(topic, self._dumps(data), qos=0, retain=False)
    
    def clear_all_discovery(self, unit_ids: list):
        logger.info("🧹 正在執行 HA 實體清除...")
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
        self.mqtt.publish(topic, "", qos=1, retain=True)
