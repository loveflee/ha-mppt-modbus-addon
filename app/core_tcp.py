import socket
import time
from typing import Optional

class RobustTCPClient:
    """
    🛡️ 工業級 TCP 連線核心 (通用版)
    功能：
    1. 負責底層 Socket 連線與重連。
    2. 實作 recv_fixed 防止封包碎片化。
    3. 實作 flush_buffer 防止讀取殘留數據。
    4. 啟用 TCP_NODELAY 降低延遲。
    """
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        try:
            self.close()
            # print(f"🔌 [TCP] 連線至 {self.host}:{self.port} ...")
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            time.sleep(0.1) # 必要緩衝
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
        """清空接收緩衝區"""
        if not self._sock: return
        try:
            self._sock.settimeout(0.01)
            while self._sock.recv(1024): pass
        except: pass
        finally:
            if self._sock: self._sock.settimeout(self.timeout)

    def send(self, data: bytes) -> bool:
        if not self._sock:
            if not self.connect(): return False
        try:
            self.flush_buffer() # 發送前總是清空，避免讀到上一輪的髒數據
            self._sock.sendall(data)
            return True
        except Exception:
            self.close()
            return False

    def recv_fixed(self, length: int) -> Optional[bytes]:
        """🛡️ 穩健接收：循環讀取直到收滿指定長度"""
        if not self._sock: return None
        chunks = []
        bytes_recd = 0
        start_time = time.time()
        
        try:
            while bytes_recd < length:
                if (time.time() - start_time) > self.timeout:
                    return None # 超時
                
                chunk = self._sock.recv(length - bytes_recd)
                if not chunk:
                    self.close()
                    return None
                
                chunks.append(chunk)
                bytes_recd += len(chunk)
            
            return b''.join(chunks)
        except Exception:
            self.close()
            return None
