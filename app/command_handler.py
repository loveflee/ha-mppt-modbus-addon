import logging
import asyncio # 引入
import mppt_register_map as rmap
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("CMD")

class AsyncCommandHandler:
    def __init__(self, protocol, timezone_offset=8):
        self.protocol = protocol
        self.tz_offset = timezone_offset

    async def process_message(self, topic: str, payload: str):
        try:
            parts = topic.split('/')
            if len(parts) < 4: return
            key, entity_base, domain = parts[-2], parts[-3], parts[-4]
            try: uid = int(entity_base.split('_')[-1])
            except: return

            # 🟢 全面改用 await
            if domain == "switch": await self._handle_switch(uid, key, payload)
            elif domain == "button": await self._handle_button(uid, key)
            elif domain == "number": await self._handle_number(uid, key, payload)
            elif domain == "select": await self._handle_select(uid, key, payload)

        except Exception as e:
            logger.error(f"指令處理錯誤: {e}")

    async def _handle_switch(self, uid, key, payload):
        switch_def = rmap.CONTROL_SWITCHES.get(key)
        if switch_def:
            cmd = switch_def['on_code'] if payload.upper() == "ON" else switch_def['off_code']
            logger.info(f"👉 [Switch] 切換 {key} -> {payload}")
            await self.protocol.write_c0_command(uid, cmd)

    async def _handle_button(self, uid, key):
        btn_def = rmap.CONTROL_BUTTONS.get(key)
        if btn_def:
            if btn_def.get('code') == 0xDF:
                local_dt = self._get_local_time()
                logger.info(f"⏰ 同步時間: {local_dt}")
                await self.protocol.write_time_sync(uid, local_dt)
            else:
                logger.info(f"👉 [Button] 觸發 {key}")
                await self.protocol.write_c0_command(uid, btn_def['code'])

    async def _handle_number(self, uid, key, payload):
        target, code = self._find_d0(key)
        if target:
            try:
                val = float(payload)
                logger.info(f"👉 [Number] 設定 {key} = {val}")
                await self.protocol.write_d0_command(uid, code, val, target['scale'], target['valid_bytes'])
            except: pass

    async def _handle_select(self, uid, key, payload):
        target, code = self._find_d0(key)
        if target:
            map_dict = None
            link = target.get('ha', {}).get('link_b1')
            for b in rmap.B1_INFO:
                if b['key'] == link: map_dict = b.get('map'); break
            
            val = None
            if map_dict:
                for k, v in map_dict.items():
                    if v == payload: val = k; break
                if val is None and ":" in payload:
                    try: val = int(payload.split(':')[0])
                    except: pass
            
            if val is not None:
                logger.info(f"👉 [Select] 設定 {key} = {payload} (ID={val})")
                await self.protocol.write_d0_command(uid, code, val, 1, target['valid_bytes'])

    def _find_d0(self, key):
        for c, i in rmap.D0_PARAMS.items():
            if i['key'] == key: return i, c
        return None, None

    def _get_local_time(self):
        return datetime.now(timezone.utc) + timedelta(hours=self.tz_offset)
