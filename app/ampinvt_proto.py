import struct
from typing import Dict, Any, List, Optional
from datetime import datetime
from core_tcp import RobustTCPClient

class AmpinvtProtocol:
    """
    📦 協議層：V4.5 新增時間同步功能 (0xDF)
    """
    def __init__(self, tcp_client: RobustTCPClient, debug: bool = False):
        self.transport = tcp_client
        self.debug = debug

    def _calc_checksum(self, data: bytes) -> int:
        return sum(data) & 0xFF

    def read_b1_data(self, unit_id: int) -> Optional[bytes]:
        req = bytearray([unit_id, 0xB1, 0x01, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        if self.debug: print(f"TX [{unit_id}] Read: {req.hex(' ')}")
        if not self.transport.send(req): return None
        resp = self.transport.recv_fixed(93)
        return resp

    def write_c0_command(self, unit_id: int, control_code: int) -> bool:
        req = bytearray([unit_id, 0xC0, control_code, 0x00, 0x00, 0x00, 0x00])
        req.append(self._calc_checksum(req))
        if self.debug: print(f"TX [{unit_id}] Write C0: {req.hex(' ')}")
        if not self.transport.send(req): return False
        resp = self.transport.recv_fixed(8)
        return bool(resp and len(resp) == 8)

    def write_d0_command(self, unit_id: int, param_code: int, value: float, scale: float, valid_bytes: list) -> bool:
        int_val = int(round(value / scale))
        req = bytearray([unit_id, 0xD0, param_code, 0x00, 0x00, 0x00, 0x00])
        if len(valid_bytes) == 1:
            req[valid_bytes[0]] = int_val & 0xFF
        elif len(valid_bytes) == 2:
            high_idx, low_idx = valid_bytes
            req[high_idx] = (int_val >> 8) & 0xFF
            req[low_idx] = int_val & 0xFF
        req.append(self._calc_checksum(req))
        
        if self.debug: print(f"TX [{unit_id}] Write D0: {req.hex(' ')}")
        if not self.transport.send(req): return False
        resp = self.transport.recv_fixed(8)
        return bool(resp and len(resp) == 8)

    def write_time_sync(self, unit_id: int, dt: datetime) -> bool:
        """🟢 [NEW] 發送 0xDF 時間同步指令"""
        # 格式: Addr, DF, Year(2碼), Month, Day, Hour, Min, Check
        year_short = dt.year % 100
        req = bytearray([
            unit_id, 
            0xDF, 
            year_short, 
            dt.month, 
            dt.day, 
            dt.hour, 
            dt.minute
        ])
        req.append(self._calc_checksum(req))
        
        if self.debug: print(f"TX [{unit_id}] Sync Time ({dt}): {req.hex(' ')}")
        
        if not self.transport.send(req): return False
        
        # 回傳通常是 8 bytes 確認
        resp = self.transport.recv_fixed(8)
        if self.debug and resp: print(f"RX [{unit_id}] Sync Resp: {resp.hex(' ')}")
        
        return bool(resp and len(resp) == 8)

    def decode(self, raw_bytes: bytes, map_list: Any, is_bits: bool = False) -> Dict[str, Any]:
        result = {}
        if is_bits:
            for key, info in map_list.items():
                if info['byte'] < len(raw_bytes):
                    is_on = bool((raw_bytes[info['byte']] >> info['bit']) & 0x01)
                    result[key] = "ON" if is_on else "OFF"
            return result

        for item in map_list:
            key, offset, length, scale = item['key'], item['offset'], item['length'], item['scale']
            if offset + length > len(raw_bytes): continue
            
            chunk = raw_bytes[offset : offset + length]
            val = 0
            try:
                if length == 1: val = chunk[0]
                elif length == 2:
                    fmt = '>h' if item['signed'] else '>H'
                    val = struct.unpack(fmt, chunk)[0]
                elif length == 4:
                    fmt = '>i' if item['signed'] else '>I'
                    val = struct.unpack(fmt, chunk)[0]
                
                if item.get('map') and val in item['map']:
                    result[key] = item['map'][val]
                else:
                    result[key] = round(val / scale, 2) if scale != 1 else val
            except: pass

        if "battery_voltage" in result and "charge_current" in result:
             try: result["charge_power"] = round(result["battery_voltage"] * result["charge_current"], 1)
             except: pass
        return result
