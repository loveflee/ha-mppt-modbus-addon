from datetime import datetime, timedelta, timezone
import mppt_register_map as rmap

class CommandHandler:
    """
    🧠 指令處理中樞
    職責：解析 MQTT Topic 與 Payload，並呼叫 Protocol 發送對應指令
    """
    def __init__(self, protocol, timezone_offset=8):
        self.protocol = protocol
        self.tz_offset = timezone_offset

    def process_message(self, topic: str, payload: str):
        """主入口：處理一條 MQTT 訊息"""
        try:
            # 解析 Topic: .../domain/entity_base/key/set
            parts = topic.split('/')
            if len(parts) < 4: return

            key = parts[-2]
            entity_base = parts[-3]
            domain = parts[-4]
            
            # 從 entity_base (例如 wifi01_mppt_1) 提取 UID
            try:
                uid = int(entity_base.split('_')[-1])
            except:
                print(f"⚠️ 無法從 {entity_base} 解析 UID")
                return

            # 根據類型分發給不同的處理函式 (策略模式)
            if domain == "switch":
                self._handle_switch(uid, key, payload)
            elif domain == "button":
                self._handle_button(uid, key)
            elif domain == "number":
                self._handle_number(uid, key, payload)
            elif domain == "select":
                self._handle_select(uid, key, payload)
            else:
                print(f"⚠️ 未知的控制類型: {domain}")

        except Exception as e:
            print(f"❌ 指令處理發生錯誤: {e}")

    def _handle_switch(self, uid, key, payload):
        switch_def = rmap.CONTROL_SWITCHES.get(key)
        if switch_def:
            cmd = switch_def['on_code'] if payload.upper() == "ON" else switch_def['off_code']
            print(f"👉 [Switch] 切換 {key} -> {payload}")
            self.protocol.write_c0_command(uid, cmd)

    def _handle_button(self, uid, key):
        btn_def = rmap.CONTROL_BUTTONS.get(key)
        if btn_def:
            code = btn_def['code']
            # 特殊處理：時間同步 (0xDF)
            if code == 0xDF:
                local_dt = self._get_local_time()
                print(f"👉 [Button] 執行時間同步: {local_dt}")
                self.protocol.write_time_sync(uid, local_dt)
            else:
                print(f"👉 [Button] 觸發 {key}")
                self.protocol.write_c0_command(uid, code)

    def _handle_number(self, uid, key, payload):
        target_item, target_code = self._find_d0_param(key)
        if target_item:
            try:
                val = float(payload)
                print(f"👉 [Number] 設定 {key} = {val}")
                self.protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])
            except ValueError:
                print(f"⚠️ 無法將 {payload} 轉為數字")

    def _handle_select(self, uid, key, payload):
        target_item, target_code = self._find_d0_param(key)
        if target_item:
            # 尋找對應的 Map
            map_dict = None
            link_key = target_item.get('ha', {}).get('link_b1')
            
            # 從 B1_INFO 找 map
            for b1_item in rmap.B1_INFO:
                if b1_item.get('key') == link_key:
                    map_dict = b1_item.get('map')
                    break
            
            if map_dict:
                int_val = self._resolve_select_value(payload, map_dict)
                if int_val is not None:
                    print(f"👉 [Select] 設定 {key} = {payload} (Val={int_val})")
                    self.protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                else:
                    print(f"⚠️ 找不到選項 '{payload}' 對應的數值")

    def _find_d0_param(self, key):
        """輔助函式：從 D0_PARAMS 查找參數設定"""
        for code, item in rmap.D0_PARAMS.items():
            if item['key'] == key:
                return item, code
        return None, None

    def _resolve_select_value(self, payload, map_dict):
        """輔助函式：解析下拉選單的值 (支援文字匹配與 ID 匹配)"""
        # 1. 嘗試完全匹配 (Value -> Key)
        for k, v in map_dict.items():
            if v == payload: return k
        
        # 2. 嘗試前綴 ID 解析 (例如 "3:鋰電池" -> 3)
        if ":" in payload:
            try:
                potential_id = int(payload.split(':')[0])
                if potential_id in map_dict: return potential_id
            except: pass
        return None

    def _get_local_time(self):
        """取得帶時區的當地時間"""
        utc_now = datetime.now(timezone.utc)
        return utc_now + timedelta(hours=self.tz_offset)
