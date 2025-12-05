import json
import queue
from dataclasses import dataclass
from typing import Any, Dict, List
import paho.mqtt.client as mqtt
import mppt_register_map as rmap 

@dataclass
class ControlCommand:
    unit_id: int
    cmd_type: str
    code: int
    value: int
    data_len: int = 0
    name: str = ""

class HomeAssistantMQTT:
    def __init__(self, config: dict, unit_ids: List[int]):
        self.broker = config['broker']
        self.port = config['port']
        self.username = config['username']
        self.password = config['password']
        self.discovery_prefix = config['discovery_prefix']
        
        self.node_id = config.get('node_id', 'wifi01') 
        self.module_name = "mppt"
        self.device_name = config['device_name']
        self.unit_ids = unit_ids
        
        self._build_command_maps()
        self.command_queue = queue.Queue()
        
        self.base_topic = f"{self.discovery_prefix}/sensor/{self.node_id}_{self.module_name}"
        self.availability_topic = f"{self.base_topic}/availability"

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.will_set(self.availability_topic, "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def _build_command_maps(self):
        self.c0_map = {}
        for code, info in getattr(rmap, 'C0_COMMANDS', {}).items():
            self.c0_map[info['key']] = {"code": code, "name": info['name']}
        self.d0_map = {}
        for code, info in getattr(rmap, 'D0_PARAMS', {}).items():
            key = info['key']
            self.d0_map[key] = {
                "code": code, "len": info['data_len'], "scale": info.get('scale', 1), "name": info['name']
            }

    def connect(self):
        try:
            print(f"📡 [MQTT] 連線至 {self.broker}:{self.port} ...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ [MQTT] 連線失敗: {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"✅ [MQTT] 已連線")
            self.client.publish(self.availability_topic, "online", retain=True)
            self.publish_discovery()
            self.client.subscribe(f"{self.discovery_prefix}/+/+/+/set")
        else:
            print(f"❌ [MQTT] 連線拒絕: {rc}")

    def publish_discovery(self):
        print("📤 發送 HA Discovery 配置 (含功率計算)...")
        for uid in self.unit_ids:
            entity_uid_base = f"{self.node_id}_{self.module_name}_{uid}"
            device_identifier = f"{self.node_id}_{self.module_name}_addr{uid}"
            
            device_info = {
                "identifiers": [device_identifier],
                "name": f"MPPT 太陽能控制器 (地址 {uid})",
                "model": "ampinvt RS485 (多設備輪詢版)",
                "manufacturer": "ampinvt",
            }

            self._register_sensors(uid, entity_uid_base, device_info, rmap.B1_INFO, "state_b1")

            for key, info in rmap.B3_STATUS_BITS.items():
                self._publish_single_discovery(
                    uid, entity_uid_base, device_info, key, info, 
                    "binary_sensor", "state_bits", is_binary=True
                )

            for code, info in getattr(rmap, 'C0_COMMANDS', {}).items():
                self._publish_control_discovery(entity_uid_base, device_info, info['key'], info['name'], "switch")

            for code, info in getattr(rmap, 'D0_PARAMS', {}).items():
                self._publish_control_discovery(entity_uid_base, device_info, info['key'], info['name'], "number", info)
        
        print(f"✅ Discovery 發送完成。")

    def _publish_single_discovery(self, uid, entity_uid_base, device_info, key, info, domain, sub_topic, is_binary=False):
        unique_id = f"{entity_uid_base}_{key}"
        if is_binary: unique_id += "_bs"

        topic = f"{self.discovery_prefix}/{domain}/{entity_uid_base}/{key}/config"
        
        payload = {
            "name": info['name'],
            "unique_id": unique_id,
            "device": device_info,
            "state_topic": f"{self.base_topic}/{uid}/{sub_topic}",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "availability_topic": self.availability_topic
        }

        if is_binary:
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
            if "device_class" in info['ha']: payload["device_class"] = info['ha']["device_class"]
        else:
            if "unit_of_measurement" in info['ha']: payload["unit_of_measurement"] = info['ha']["unit_of_measurement"]
            elif info.get('unit'): payload["unit_of_measurement"] = info['unit']
            for f in ["device_class", "state_class", "icon"]:
                if f in info['ha']: payload[f] = info['ha'][f]

        self.client.publish(topic, json.dumps(payload), retain=True)

    def _register_sensors(self, uid, entity_uid_base, device_info, map_list, sub_topic):
        for item in map_list:
            if "ha" not in item: continue
            if item['ha'].get('type') != 'sensor': continue
            self._publish_single_discovery(uid, entity_uid_base, device_info, item['key'], item, "sensor", sub_topic)

    def _publish_control_discovery(self, entity_uid_base, device_info, key, name, domain, extra_info=None):
        unique_id = f"{entity_uid_base}_{key}"
        topic = f"{self.discovery_prefix}/{domain}/{entity_uid_base}/{key}/config"
        
        payload = {
            "name": name,
            "unique_id": unique_id,
            "device": device_info,
            "command_topic": f"{self.discovery_prefix}/{domain}/{entity_uid_base}/{key}/set",
            "availability_topic": self.availability_topic
        }

        if domain == "switch":
            payload["state_topic"] = f"{self.discovery_prefix}/{domain}/{entity_uid_base}/{key}/state"
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
            payload["icon"] = "mdi:toggle-switch"
        
        elif domain == "number":
            read_key = key.replace("set_", "")
            try: unit_id = entity_uid_base.split('_')[-1]
            except: unit_id = "1"
            payload["state_topic"] = f"{self.base_topic}/{unit_id}/state_b1"
            payload["value_template"] = f"{{{{ value_json.{read_key} }}}}"
            max_val = 65535
            step = 1
            if extra_info:
                if extra_info.get('scale', 1) == 0.01: 
                    step = 0.01
                    max_val = 200
                if "unit" in extra_info: payload["unit_of_measurement"] = extra_info["unit"]
            payload["min"] = 0
            payload["max"] = max_val
            payload["step"] = step
            payload["mode"] = "box"

        self.client.publish(topic, json.dumps(payload), retain=True)

    def publish_states(self, unit_id: int, data: Dict[str, Any], sub_topic: str):
        if not data: return
        
        # 🟢 [新增] 自動計算功率 (P = V * I)
        # 邏輯：如果收到的資料包含電壓和電流，就自動算出功率並加入 payload
        if "battery_voltage" in data and "charge_current" in data:
            try:
                v = float(data["battery_voltage"])
                i = float(data["charge_current"])
                data["charge_power"] = round(v * i, 2)
            except Exception:
                pass # 忽略計算錯誤，維持原樣

        topic = f"{self.base_topic}/{unit_id}/{sub_topic}"
        self.client.publish(topic, json.dumps(data), retain=True)

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            parts = topic.split('/')
            if len(parts) < 5 or parts[-1] != "set": return
            node_uid = parts[-3]
            key = parts[-2]
            try: target_unit = int(node_uid.split('_')[-1])
            except: return
            if target_unit not in self.unit_ids: return

            if key in self.c0_map:
                info = self.c0_map[key]
                if payload == "ON":
                      cmd = ControlCommand(target_unit, "C0", info['code'], 0, name=info['name'])
                      self.command_queue.put(cmd)
                      state_topic = f"{self.discovery_prefix}/switch/{node_uid}/{key}/state"
                      self.client.publish(state_topic, "OFF", retain=False)
                      self.client.publish(state_topic, "ON", retain=False)

            elif key in self.d0_map:
                info = self.d0_map[key]
                try: raw_value = float(payload)
                except: return
                scale = info['scale']
                encoded_value = int(round(raw_value / scale)) if scale != 0 else int(raw_value)
                cmd = ControlCommand(target_unit, "D0", info['code'], encoded_value, info['len'], name=info['name'])
                self.command_queue.put(cmd)

        except Exception as e:
            print(f"⚠ MQTT Error: {e}")
