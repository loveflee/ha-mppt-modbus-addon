import logging
from datetime import datetime
from core_tcp import AsyncTCPClient # 引用新的 Client

logger = logging.getLogger("Proto")

class AsyncAmpinvtProtocol:
    """
    📦 V6.0 非同步協議層
    負責封包的打包與校驗，底層呼叫 AsyncTCPClient
    """
    def __init__(self, tcp_client: AsyncTCPClient, debug: bool = False):
        self.transport = tcp_client
        self.debug = debug

    def _calc_checksum(self, data: bytes) -> int:
        return sum(data) & 0xFF

    async def read_b1_data(self, unit_id: int):
        req = bytearray([unit_id, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        
        if self.debug: logger.debug(f"TX [{unit_id}] Read: {req.hex(' ')}")
        
        if not await self.transport.send(req): return None
        resp = await self.transport.recv_fixed(93)
        
        if self.debug and resp: logger.debug(f"RX [{unit_id}]: {resp.hex(' ')}")
        if not resp: return None
        
        if self._calc_checksum(resp[:-1]) != resp[-1]: 
            if self.debug: logger.warning(f"⚠️ [{unit_id}] 校驗錯誤")
            return None
        return resp

    async def write_c0_command(self, unit_id: int, control_code: int) -> bool:
        req = bytearray([unit_id, 0xC0, control_code, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        
        if self.debug: logger.info(f"TX [{unit_id}] Write C0: {req.hex(' ')}")
        
        if not await self.transport.send(req): return False
        resp = await self.transport.recv_fixed(8)
        return bool(resp and len(resp) == 8)

    async def write_d0_command(self, unit_id: int, code: int, val: float, scale: float, vbytes: list) -> bool:
        int_val = int(round(val / scale))
        req = bytearray([unit_id, 0xD0, code, 0x00, 0x00, 0x00, 0x00])
        
        if len(vbytes) == 1: req[vbytes[0]] = int_val & 0xFF
        elif len(vbytes) == 2:
            req[vbytes[0]] = (int_val >> 8) & 0xFF
            req[vbytes[1]] = int_val & 0xFF
            
        req.append(self._calc_checksum(req))
        
        if self.debug: logger.info(f"TX [{unit_id}] Write D0: {req.hex(' ')}")
        
        if not await self.transport.send(req): return False
        resp = await self.transport.recv_fixed(8)
        return bool(resp and len(resp) == 8)

    async def write_time_sync(self, unit_id: int, dt: datetime) -> bool:
        req = bytearray([unit_id, 0xDF, dt.year % 100, dt.month, dt.day, dt.hour, dt.minute])
        req.append(self._calc_checksum(req))
        
        if self.debug: logger.info(f"TX [{unit_id}] TimeSync: {req.hex(' ')}")
        
        if not await self.transport.send(req): return False
        resp = await self.transport.recv_fixed(8)
        return bool(resp and len(resp) == 8)

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
                if ln == 1: val = chunk[0]
                elif ln == 2: val = struct.unpack('>h' if item['signed'] else '>H', chunk)[0]
                elif ln == 4: val = struct.unpack('>i' if item['signed'] else '>I', chunk)[0]
                
                if item.get('map') and val in item['map']: result[key] = item['map'][val]
                else: result[key] = round(val / sc, 2) if sc != 1 else val
            except: pass
            
        if "battery_voltage" in result and "charge_current" in result:
             try: result["charge_power"] = round(result["battery_voltage"] * result["charge_current"], 1)
             except: pass
        return result


