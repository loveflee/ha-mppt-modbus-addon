import socket
import time
import logging

logger = logging.getLogger("TCP")

class RobustTCPClient:
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None

    def connect(self) -> bool:
        try:
            self.close() 
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
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
                self._sock.close()
            except: pass
        self._sock = None

    def flush_buffer(self):
        """🔥 優化：強制清空緩衝區，防止讀到舊資料"""
        if not self._sock: return
        try:
            self._sock.settimeout(0.05)
            while True:
                chunk = self._sock.recv(4096)
                if not chunk: break
        except socket.timeout: pass
        except Exception: self.close()
        finally:
            if self._sock: self._sock.settimeout(self.timeout)

    def send(self, data: bytes) -> bool:
        if not self._sock:
            if not self.connect(): return False
        try:
            self.flush_buffer()
            self._sock.sendall(data)
            return True
        except Exception:
            self.close()
            return False

    def recv_fixed(self, length: int) -> bytes:
        if not self._sock: return None
        data = b''
        start_time = time.time()
        try:
            while len(data) < length:
                if (time.time() - start_time) > self.timeout:
                    if len(data) > 0:
                        logger.warning(f"⚠️ 接收超時，僅收到 {len(data)}/{length} bytes")
                    return None
                
                needed = length - len(data)
                chunk = self._sock.recv(needed)
                
                if not chunk:
                    self.close(); return None
                data += chunk
            return data
        except socket.timeout: return None
        except Exception as e:
            logger.error(f"接收錯誤: {e}")
            self.close()
            return None
