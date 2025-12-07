import socket
import time
import logging

logger = logging.getLogger("TCP")

class RobustTCPClient:
    """
    🛡️ V5.5 工業級同步 TCP 客戶端 (Socket版)
    特點：簡單、粗暴、穩定。適合對時序敏感的 RS485 設備。
    """
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None

    def connect(self) -> bool:
        try:
            self.close()
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 停用 Nagle 演算法，讓指令不延遲直接送出
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            time.sleep(0.1) # 物理連線後的必要緩衝
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
        """暴力清空緩衝區，確保沒有殘留數據"""
        if not self._sock: return
        try:
            self._sock.settimeout(0.01) # 極短超時
            while True:
                data = self._sock.recv(1024)
                if not data: break
        except socket.timeout:
            pass # 讀不到東西代表乾淨了
        except:
            pass
        finally:
            if self._sock: self._sock.settimeout(self.timeout)

    def send(self, data: bytes) -> bool:
        if not self._sock:
            if not self.connect(): return False
        try:
            self.flush_buffer() # 發送前先清空
            self._sock.sendall(data)
            return True
        except Exception:
            self.close()
            return False

    def recv_fixed(self, length: int) -> bytes:
        """死纏爛打讀取法：一定要讀滿 length 個字節"""
        if not self._sock: return None
        data = b''
        start_time = time.time()
        
        try:
            while len(data) < length:
                if (time.time() - start_time) > self.timeout:
                    return None # 超時
                
                chunk = self._sock.recv(length - len(data))
                if not chunk:
                    self.close()
                    return None
                data += chunk
            return data
        except Exception:
            self.close()
            return None
