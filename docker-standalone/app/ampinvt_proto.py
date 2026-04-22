# 通訊與解碼心臟
import logging
from datetime import datetime
from core_tcp import RobustTCPClient

logger = logging.getLogger("Proto")

class AmpinvtProtocol:
    def __init__(self, tcp_client: RobustTCPClient, debug: bool = False):
        self.transport = tcp_client
        self.debug = debug

    def _calc_checksum(self, data: bytes) -> int:
        return sum(data) & 0xFF

    # 🛡️ 技師重刀：寫入操作的嚴格驗證器 (擋下 0xEE 錯誤與壞包)
    def _verify_write_response(self, resp: bytes) -> bool:
        if not resp or len(resp) != 8:
            if self.debug: logger.warning("❌ 寫入回應長度異常或無回應")
            return False
        
        # 1. 驗證 Checksum
        if self._calc_checksum(resp[:-1]) != resp[-1]:
            logger.warning("❌ 寫入回應 Checksum 錯誤")
            return False
            
        # 2. 攔截 0xEE 設備拒絕代碼
        if resp[1] == 0xEE:
            err_map = {1: "當前狀態不能完成操作", 2: "不能識別的參數代碼", 3: "參數數據溢出"}
            err_msg = err_map.get(resp[2], f"未知錯誤碼 ({resp[2]})")
            logger.error(f"❌ 設備拒絕指令: {err_msg}")
            return False
            
        return True

    def read_b1_data(self, unit_id: int):
        req = bytearray([unit_id, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        if self.debug: logger.debug(f"TX [{unit_id}] Read: {req.hex(' ')}")
        if not self.transport.send(req): return None
        resp = self.transport.recv_fixed(93)
        if self.debug and resp: logger.debug(f"RX [{unit_id}]: {resp.hex(' ')}")
        if not resp or len(resp) != 93: return None
        if self._calc_checksum(resp[:-1]) != resp[-1]: return None
        return resp

    def write_c0_command(self, unit_id: int, control_code: int) -> bool:
        req = bytearray([unit_id, 0xC0, control_code, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        if self.debug: logger.info(f"TX [{unit_id}] Write C0: {req.hex(' ')}")
        if not self.transport.send(req): return False
        resp = self.transport.recv_fixed(8)
        return self._verify_write_response(resp) # 🛡️ 套用嚴格驗證

    # 🔥 修改：支援 val 傳入字串 "HH:MM"，並轉譯為 4 Byte BCD 下發給設備
    def write_d0_command(self, unit_id: int, code: int, val, scale: float, vbytes: list) -> bool:
        req = bytearray([unit_id, 0xD0, code, 0x00, 0x00, 0x00, 0x00])
        
        # 判斷是否為時控字串 (例如 "08:30")
        if isinstance(val, str) and ":" in val:
            try:
                h, m = map(int, val.split(":"))
                req[3] = h // 10  # 時十位
                req[4] = h % 10   # 時個位
                req[5] = m // 10  # 分十位
                req[6] = m % 10   # 分個位
            except ValueError:
                logger.error(f"❌ 無效的時間格式: {val}")
                return False
        else:
            # 一般數字處理邏輯
            int_val = int(round(float(val) / scale))
            if len(vbytes) == 1: 
                req[vbytes[0]] = int_val & 0xFF
            elif len(vbytes) == 2:
                req[vbytes[0]] = (int_val >> 8) & 0xFF
                req[vbytes[1]] = int_val & 0xFF

        req.append(self._calc_checksum(req))
        if self.debug: logger.info(f"TX [{unit_id}] Write D0: {req.hex(' ')}")
        if not self.transport.send(req): return False
        resp = self.transport.recv_fixed(8)
        return self._verify_write_response(resp) # 🛡️ 套用嚴格驗證

    def write_time_sync(self, unit_id: int, dt: datetime) -> bool:
        req = bytearray([unit_id, 0xDF, dt.year % 100, dt.month, dt.day, dt.hour, dt.minute])
        req.append(self._calc_checksum(req))
        if self.debug: logger.info(f"TX [{unit_id}] TimeSync: {req.hex(' ')}")
        if not self.transport.send(req): return False
        resp = self.transport.recv_fixed(8)
        return self._verify_write_response(resp) # 🛡️ 套用嚴格驗證

    # 🔥 修改：加入 bcd_time 攔截器，將 4 byte 解析回字串 "HH:MM"
    def decode(self, raw_bytes, map_list, is_bits=False):
        import struct
        result = {}
        if is_bits:
            for key, info in map_list.items():
                if info['byte'] < len(raw_bytes):
                    is_on = bool((raw_bytes[info['byte']] >> info['bit']) & 0x01)
                    result[key] = "ON" if is_on else "OFF"
            return result
            
        for item in map_list:
            key, off, ln, sc = item['key'], item['offset'], item['length'], item['scale']
            if off + ln > len(raw_bytes): continue
            chunk = raw_bytes[off : off + ln]
            val = 0
            try:
                # 💡 時控解碼攔截點
                if item.get("bcd_time") and ln == 4:
                    h = chunk[0] * 10 + chunk[1]
                    m = chunk[2] * 10 + chunk[3]
                    result[key] = f"{h:02d}:{m:02d}"
                    continue  # 直接跳到下一個點位，不執行後面的數字解析

                if ln == 1: val = chunk[0]
                elif ln == 2: val = struct.unpack('>h' if item.get('signed') else '>H', chunk)[0]
                elif ln == 4: val = struct.unpack('>i' if item.get('signed') else '>I', chunk)[0]
                
                if item.get('map') and val in item['map']: 
                    result[key] = item['map'][val]
                else: 
                    result[key] = round(val / sc, 2) if sc != 1 else val
            except Exception as e:
                if self.debug: logger.warning(f"解碼錯誤 {key}: {e}")
                pass
                
        if "battery_voltage" in result and "charge_current" in result:
             try: result["charge_power"] = round(result["battery_voltage"] * result["charge_current"], 1)
             except: pass
        return result
