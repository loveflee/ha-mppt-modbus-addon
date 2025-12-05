import socket
import time
from typing import Optional

class ModbusClient:
    """
    📌 佛山金廣源 MPPT 專用通訊客戶端
    
    🛠 修復說明 (V1.4):
    1. [關鍵] 取消去頭去尾：read_mppt_b1_full 現在回傳完整的 93 Bytes。
       這確保了 mppt_register_map.py 中的 Offset (如 PV=30) 與手冊/舊程式完全對應。
    2. [穩定性] 保持 _recv_fixed 機制，防止封包碎片化。
    """
    
    def __init__(self, config: dict, debug: bool = False):
        self.host = config['host']
        self.port = config['port']
        self.timeout = config.get('timeout', 3.0) 
        self.retry_delay = config.get('retry_delay', 2.0)
        self.debug = debug
        self._sock: Optional[socket.socket] = None

    def connect(self):
        try:
            if self._sock: self.close()
            if self.debug: print(f"🔌 [Modbus] 連線至 {self.host}:{self.port} ...")

            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            time.sleep(0.1)
            return True
        except Exception:
            self._sock = None
            return False

    def close(self):
        if self._sock:
            try: self._sock.close()
            except: pass
        self._sock = None

    def ensure_connection(self):
        if self._sock is None:
            if not self.connect(): time.sleep(self.retry_delay)

    def _flush_buffer(self):
        if not self._sock: return
        try:
            self._sock.settimeout(0.01)
            while self._sock.recv(1024): pass
        except: pass
        finally:
            if self._sock: self._sock.settimeout(self.timeout)

    def _calc_checksum(self, data: bytes) -> int:
        return sum(data) & 0xFF

    def _recv_fixed(self, length: int) -> bytes:
        chunks = []
        bytes_recd = 0
        self._sock.settimeout(self.timeout)
        start_time = time.time()
        
        while bytes_recd < length:
            if (time.time() - start_time) > self.timeout: break
            try:
                chunk = self._sock.recv(length - bytes_recd)
                if not chunk: break
                chunks.append(chunk)
                bytes_recd += len(chunk)
            except socket.timeout: break
            except Exception: break
        return b''.join(chunks)

    def _send_recv_raw(self, unit_id: int, request_frame: bytes, expected_len: int) -> Optional[bytes]:
        self.ensure_connection()
        if not self._sock: return None

        try:
            self._flush_buffer()
            if self.debug: 
                print(f"TX [ID:{unit_id}]: " + " ".join([f"{b:02X}" for b in request_frame]))
            
            self._sock.sendall(request_frame)
            response = self._recv_fixed(expected_len)
            
            if self.debug and response: 
                # 這裡印出的 RX 會跟您提供的 Hex Dump 一模一樣
                print(f"RX [ID:{unit_id}]: " + " ".join([f"{b:02X}" for b in response]))

            if len(response) != expected_len:
                if self.debug: print(f"⚠ 長度不符: 預期 {expected_len}, 收到 {len(response)}")
                return None
            
            # 校驗檢查 (排除最後一個 Byte 的 checksum 本身)
            if self._calc_checksum(response[:-1]) != response[-1]:
                if self.debug: print("⚠ 校驗碼錯誤")
                return None

            # ✅ 關鍵修改：回傳完整封包，不做切割！
            # 這樣 Offset 0 就是地址，Offset 30 就是 PV 電壓，完全對應舊程式。
            return response 

        except Exception as e:
            if self.debug: print(f"❌ 通訊例外: {e}")
            self.close()
            return None

    def _build_packet(self, unit_id: int, cmd: int) -> bytearray:
        packet = bytearray([unit_id, cmd, 0x01, 0x00, 0x00, 0x00, 0x00])
        packet.append(self._calc_checksum(packet))
        return packet

    def read_mppt_b1_full(self, unit_id: int) -> Optional[bytes]:
        req = self._build_packet(unit_id, 0xB1)
        return self._send_recv_raw(unit_id, req, 93)

    # 寫入指令部分 (回傳 8 bytes)
    def write_mppt_command(self, unit_id: int, control_code: int) -> bool:
        packet = bytearray([unit_id, 0xC0, control_code, 0x00, 0x00, 0x00, 0x00])
        packet.append(self._calc_checksum(packet))
        resp = self._send_recv_raw(unit_id, bytes(packet), 8)
        return True if resp else False

    def write_mppt_setting(self, unit_id: int, param_code: int, value: int, data_len: int) -> bool:
        packet = bytearray([unit_id, 0xD0, param_code, 0x00, 0x00, 0x00, 0x00])
        if data_len == 1: packet[6] = value & 0xFF
        elif data_len == 2:
            packet[5] = (value >> 8) & 0xFF
            packet[6] = value & 0xFF
        elif data_len == 4:
            packet[3] = (value >> 24) & 0xFF
            packet[4] = (value >> 16) & 0xFF
            packet[5] = (value >> 8) & 0xFF
            packet[6] = value & 0xFF
        packet.append(self._calc_checksum(packet))
        resp = self._send_recv_raw(unit_id, bytes(packet), 8)
        return True if resp else False
    
    def write_clock_sync(self, unit_id: int) -> bool:
        now = time.localtime()
        packet = bytearray([unit_id, 0xDF, now.tm_year % 100, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min])
        packet.append(self._calc_checksum(packet))
        resp = self._send_recv_raw(unit_id, bytes(packet), 8)
        return True if resp else False
