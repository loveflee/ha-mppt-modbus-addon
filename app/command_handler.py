import logging
import mppt_register_map as rmap
from datetime import datetime, timedelta, timezone

# 🟢 取得專屬的 Logger，名稱會自動變成 "command_handler"
logger = logging.getLogger("CMD")

class CommandHandler:
    def __init__(self, protocol, timezone_offset=8):
        self.protocol = protocol
        self.tz_offset = timezone_offset

    def process_message(self, topic: str, payload: str):
        try:
            parts = topic.split('/')
            if len(parts) < 4: return

            key = parts[-2]
            entity_base = parts[-3]
            domain = parts[-4]
            
            try:
                uid = int(entity_base.split('_')[-1])
            except:
                logger.warning(f"無法從 {entity_base} 解析設備 ID")
                return

            if domain == "switch":
                self._handle_switch(uid, key, payload)
            elif domain == "button":
                self._handle_button(uid, key)
            elif domain == "number":
                self._handle_number(uid, key, payload)
            elif domain == "select":
                self._handle_select(uid, key, payload)
            else:
                logger.debug(f"忽略未知的控制類型: {domain}")

        except Exception as e:
            logger.error(f"指令處理發生錯誤: {e}", exc_info=True)

    def _handle_switch(self, uid, key, payload):
        switch_def = rmap.CONTROL_SWITCHES.get(key)
        if switch_def:
            cmd = switch_def['on_code'] if payload.upper() == "ON" else switch_def['off_code']
            logger.info(f"👉 [Switch] 切換 {key} -> {payload}")
            self.protocol.write_c0_command(uid, cmd)

    def _handle_button(self, uid, key):
        btn_def = rmap.CONTROL_BUTTONS.get(key)
        if btn_def:
            code = btn_def['code']
            if code == 0xDF:
                local_dt = self._get_local_time()
                logger.info(f"⏰ [Button] 執行時間同步: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                self.protocol.write_time_sync(uid, local_dt)
            else:
                logger.info(f"👉 [Button] 觸發 {key}")
                self.protocol.write_c0_command(uid, code)

    def _handle_number(self, uid, key, payload):
        target_item, target_code = self._find_d0_param(key)
        if target_item:
            try:
                val = float(payload)
                logger.info(f"👉 [Number] 設定參數 {key} = {val}")
                self.protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])
            except ValueError:
                logger.warning(f"數值格式錯誤: {payload}")

    def _handle_select(self, uid, key, payload):
        target_item, target_code = self._find_d0_param(key)
        if target_item:
            # 尋找 Map
            map_dict = None
            link_key = target_item.get('ha', {}).get('link_b1')
            for b1_item in rmap.B1_INFO:
                if b1_item.get('key') == link_key:
                    map_dict = b1_item.get('map'); break
            
            if map_dict:
                int_val = self._resolve_select_value(payload, map_dict)
                if int_val is not None:
                    logger.info(f"👉 [Select] 設定模式 {key} = {payload} (Val={int_val})")
                    self.protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                else:
                    logger.warning(f"找不到選項 '{payload}' 對應的數值")

    def _find_d0_param(self, key):
        for code, item in rmap.D0_PARAMS.items():
            if item['key'] == key: return item, code
        return None, None

    def _resolve_select_value(self, payload, map_dict):
        for k, v in map_dict.items():
            if v == payload: return k
        if ":" in payload:
            try:
                pid = int(payload.split(':')[0])
                if pid in map_dict: return pid
            except: pass
        return None

    def _get_local_time(self):
        utc_now = datetime.now(timezone.utc)
        return utc_now + timedelta(hours=self.tz_offset)
