import asyncio
import logging
import socket

logger = logging.getLogger("TCP")

class AsyncTCPClient:
    """
    ⚡ V6.0 非同步 TCP 客戶端 (工業級)
    特點：
    1. 使用 asyncio 實現非阻塞 I/O
    2. 支援 TCP_NODELAY 降低 Modbus 延遲
    3. 內建自動重連與資源清理
    """
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None

    async def connect(self) -> bool:
        """建立非同步連線"""
        try:
            await self.close() # 確保舊連線已清理
            
            # 建立連線 (設定超時)
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), 
                timeout=self.timeout
            )
            
            # 🟢 [優化] 設定 TCP_NODELAY (停用 Nagle 演算法)，讓小封包立刻送出
            sock = self.writer.get_extra_info('socket')
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
            return True
        except (asyncio.TimeoutError, OSError) as e:
            # logger.debug(f"連線失敗: {e}") 
            return False

    async def close(self):
        """優雅關閉資源"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except: pass
        self.reader = None
        self.writer = None

    async def flush_buffer(self):
        """
        🧹 清空緩衝區
        在發送指令前，先讀掉網路上殘留的垃圾數據，避免解碼錯誤
        """
        if not self.reader: return
        try:
            # 使用極短 timeout 快速讀取，直到沒東西
            while True:
                try:
                    await asyncio.wait_for(self.reader.read(1024), timeout=0.01)
                except asyncio.TimeoutError:
                    break
        except: pass

    async def send(self, data: bytes) -> bool:
        """發送數據"""
        if not self.writer:
            if not await self.connect(): return False
        
        try:
            await self.flush_buffer() # 發送前大掃除
            self.writer.write(data)
            await self.writer.drain() # 等待數據完全推入網路緩衝區
            return True
        except Exception:
            await self.close()
            return False

    async def recv_fixed(self, length: int) -> bytes:
        """
        🛡️ 穩健接收：確保收滿指定長度 (防止封包破碎)
        """
        if not self.reader: return None
        
        try:
            # readexactly 保證讀滿 N 個字節，否則拋出 IncompleteReadError
            data = await asyncio.wait_for(
                self.reader.readexactly(length), 
                timeout=self.timeout
            )
            return data
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            await self.close()
            return None
        except Exception as e:
            logger.error(f"接收異常: {e}")
            await self.close()
            return None


