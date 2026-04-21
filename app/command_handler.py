import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("CMD")

class CommandHandler:
    # 🟢 接收 rmap
    def __init__(self, protocol, ha_mgr, rmap, timezone_offset=8):
        self.protocol = protocol
        self.ha_mgr = ha_mgr
        self.rmap = rmap # 儲存
        self.tz_offset = timezone_offset

    def process_message(self, topic: str, payload: str):
        try:
            parts = topic.split('/')
            if len(parts) < 4: return
            key, entity_base, domain = parts[-2], parts[-3], parts[-4]
            try: uid = int(entity_base.split('_')[-1])
            except: return

            if domain == "switch": self._handle_switch(uid, key, payload)
            elif domain == "button": self._handle_button(uid, key)
            elif domain == "number": self._handle_number(uid, key, payload)
            elif domain == "select": self._handle_select(uid, key, payload)
            elif domain == "text": self._handle_text(uid, key, payload) # 👇 修正：新增 text 路由

        except Exception as e:
            logger.error(f"指令處理錯誤: {e}")

    def _write_and_verify(self, uid, write_func, *args):
        time.sleep(0.3)
        if write_func(*args):
            logger.info("⚡ 寫入成功，準備回讀狀態...")
            time.sleep(0.5) 
            raw_data = self.protocol.read_b1_data(uid)
            if raw_data:
                logger.info("✅ 回讀成功，更新 HA")
                # 使用 self.rmap
                vals = self.protocol.decode(raw_data, self.rmap.B1_INFO)
                bits = self.protocol.decode(raw_data, self.rmap.B3_STATUS_BITS, is_bits=True)
                self.ha_mgr.publish_state(uid, vals, "state_b1")
                self.ha_mgr.publish_state(uid, bits, "state_bits")
            else:
                logger.warning("⚠️ 回讀失敗")
        else:
            logger.warning("⚠️ 寫入無回應，嘗試重送...")
            time.sleep(1.0)
            if write_func(*args): logger.info("✅ 重送成功")
            else: logger.error("❌ 寫入最終失敗")

    def _handle_switch(self, uid, key, payload):
        switch_def = self.rmap.CONTROL_SWITCHES.get(key)
        if switch_def:
            cmd = switch_def['on_code'] if payload.upper() == "ON" else switch_def['off_code']
            logger.info(f"👉 [Switch] 切換 {key} -> {payload}")
            self._write_and_verify(uid, self.protocol.write_c0_command, uid, cmd)

    def _handle_button(self, uid, key):
        btn_def = self.rmap.CONTROL_BUTTONS.get(key)
        if btn_def:
            if btn_def.get('code') == 0xDF:
                local_dt = datetime.now(timezone.utc) + timedelta(hours=self.tz_offset)
                logger.info(f"⏰ 同步時間: {local_dt}")
                self.protocol.write_time_sync(uid, local_dt)
            else:
                logger.info(f"👉 [Button] 觸發 {key}")
                self._write_and_verify(uid, self.protocol.write_c0_command, uid, btn_def['code'])

    def _handle_number(self, uid, key, payload):
        target, code = self._find_d0(key)
        if target:
            try:
                val = float(payload)
                logger.info(f"👉 [Number] 設定 {key} = {val}")
                self._write_and_verify(uid, self.protocol.write_d0_command, uid, code, val, target['scale'], target['valid_bytes'])
            except: pass

    def _handle_select(self, uid, key, payload):
        target, code = self._find_d0(key)
        if target:
            ha_conf = target.get('ha', {})
            map_dict = None
            link = ha_conf.get('link_b1')
            
            # 尋找對應的 mapping 字典
            for b in self.rmap.B1_INFO:
                if b['key'] == link: 
                    map_dict = b.get('map')
                    break
                    
            val = None
            if map_dict:
                for k, v in map_dict.items():
                    if v == payload: 
                        val = k
                        break
                        
            # 👇 修正：如果沒有 link_b1 (樂觀模式)，直接比對 options 陣列的 Index
            if val is None and ha_conf.get('optimistic'):
                options = ha_conf.get('options', [])
                if payload in options:
                    val = options.index(payload)

            if val is not None:
                logger.info(f"👉 [Select] 設定 {key} = {payload} (ID={val})")
                self._write_and_verify(uid, self.protocol.write_d0_command, uid, code, val, 1, target['valid_bytes'])

    # 👇 修正：新增獨立的 text 處理函數 (專門處理 "HH:MM" 字串)
    def _handle_text(self, uid, key, payload):
        target, code = self._find_d0(key)
        if target:
            logger.info(f"👉 [Text] 設定 {key} = {payload}")
            # payload 已經是 "HH:MM" 字串，直接傳給 protocol 處理 BCD 轉換
            self._write_and_verify(uid, self.protocol.write_d0_command, uid, code, payload, 1, target['valid_bytes'])

    def _find_d0(self, key):
        for c, i in self.rmap.D0_PARAMS.items():
            if i['key'] == key: return i, c
        return None, None
