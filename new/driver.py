# =============================================================================
# File: driver.py
# Description: 工業級協議盲目 TCP→RS485 驅動層 V1.2 (Manus 審查強化版)
# Features:
#   1. TCP 重連風暴防護 (1s 避讓冷卻) 與 FD 洩漏警報。
#   2. 接收端 OOM 防護 (max_response_bytes 斬斷無窮雜訊)。
#   3. Modbus Exception 終極防護 (核對 Slave ID 與合法 Error Code)。
#   4. Disconnect 鎖同步，確保 I/O 原子性不被外力強制中斷。
# =============================================================================

import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class DriverTimeoutError(Exception):
    """硬體層無回應或物理干擾拋出，交由 Bus Master 處置"""
    pass

class RobustAsyncTcpDriver:
    def __init__(self, host: str, port: int,
                 timeout: float = 1.0,
                 inter_frame_delay: float = 0.18,
                 connect_timeout: float = 5.0,
                 idle_timeout: float = 0.03,
                 max_response_bytes: int = 1024):
        
        self.host = host
        self.port = port
        self.timeout = timeout
        self.inter_frame_delay = inter_frame_delay
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        self.max_response_bytes = max_response_bytes

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_comm_time: float = 0.0
        self._io_lock = asyncio.Lock()

    # =========================================================================
    # 連線與資源管理
    # =========================================================================

    async def connect(self) -> bool:
        try:
            logger.info(f"[Driver] 連線 {self.host}:{self.port} (timeout={self.connect_timeout}s)")
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout
            )
            logger.info("[Driver] 連線成功")
            return True
        except asyncio.TimeoutError:
            logger.error(f"[Driver] 連線 Timeout ({self.connect_timeout}s)")
            return False
        except Exception as e:
            logger.error(f"[Driver] 連線失敗: {e}")
            return False

    async def disconnect(self):
        """安全斷線：搶佔 I/O 鎖確保不在通訊中途強制關閉，並記錄 FD 釋放異常"""
        async with self._io_lock:
            writer = self._writer
            self._reader = None
            self._writer = None
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception as e:
                    logger.error(f"[Driver] 關閉連線異常 (可能發生資源洩漏): {e}")
            logger.info("[Driver] 已斷線")

    async def _reconnect(self):
        """死連線重建與重連風暴防護 (Exponential Backoff / Cooldown)"""
        logger.warning("[Driver] 偵測到死連線，嘗試重連...")
        await self.disconnect()
        
        await asyncio.sleep(1.0) # 強制冷卻，防 CPU 與網路資源耗盡
        
        success = await self.connect()
        if not success:
            raise DriverTimeoutError("TCP 重連失敗")
        logger.info("[Driver] 重連成功")

    # =========================================================================
    # 底層盲發盲收
    # =========================================================================

    async def _flush_buffer(self, max_bytes: int = 4096):
        if not self._reader:
            return
        flushed = 0
        try:
            while flushed < max_bytes:
                chunk = await asyncio.wait_for(self._reader.read(1024), timeout=0.01)
                if not chunk:
                    break
                flushed += len(chunk)
                logger.debug(f"[Driver] 丟棄殘留 {len(chunk)}B: {chunk.hex()}")
        except asyncio.TimeoutError:
            pass  
        except Exception as e:
            logger.warning(f"[Driver] Flush 異常: {e}")

        if flushed >= max_bytes:
            logger.warning(f"[Driver] Flush 達上限 {max_bytes}B，總線可能存在持續雜訊源！")

    async def _enforce_inter_frame_delay(self):
        elapsed = time.time() - self._last_comm_time
        if elapsed < self.inter_frame_delay:
            await asyncio.sleep(self.inter_frame_delay - elapsed)

    async def _send_and_recv(self, payload: bytes) -> bytes:
        async with self._io_lock:
            reader = self._reader
            writer = self._writer

            if not reader or not writer:
                raise DriverTimeoutError("未連線或連線已中斷")

            await self._enforce_inter_frame_delay()
            await self._flush_buffer()

            try:
                writer.write(payload)
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"[Driver] 發送失敗 (死連線): {e}")
                await self._reconnect()
                raise DriverTimeoutError("發送失敗，已觸發重連")

            raw_response = bytearray()
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=self.timeout)
                if not chunk:
                    logger.warning("[Driver] 對端關閉連線 (TCP FIN)")
                    await self._reconnect()
                    raise DriverTimeoutError("對端關閉連線，已觸發重連")
                raw_response.extend(chunk)

                # Idle-Timeout 碎包拼接與 OOM 記憶體防護
                while True:
                    if len(raw_response) >= self.max_response_bytes:
                        logger.error(f"[Driver] 接收溢出 (> {self.max_response_bytes}B)，斬斷異常封包")
                        raise DriverTimeoutError("接收緩衝區溢出 (可能遭受雜訊攻擊)")

                    try:
                        chunk = await asyncio.wait_for(reader.read(1024), timeout=self.idle_timeout)
                        if not chunk:
                            break
                        raw_response.extend(chunk)
                    except asyncio.TimeoutError:
                        break  

            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"[Driver] 接收失敗 (死連線): {e}")
                await self._reconnect()
                raise DriverTimeoutError("接收失敗，已觸發重連")
            except asyncio.TimeoutError:
                self._last_comm_time = time.time()
                raise DriverTimeoutError("設備無回應 (Timeout)")

            self._last_comm_time = time.time()
            return bytes(raw_response)

    # =========================================================================
    # Bus Master 介面合約
    # =========================================================================

    async def write(self, payload: bytes) -> bool:
        resp = await self._send_and_recv(payload)

        # Modbus Exception 終極精確探測 (長度 + Slave ID + FC + 合法 Error Code)
        if len(resp) == 5 and len(payload) >= 2:
            if resp[0] == payload[0] and (1 <= resp[2] <= 4):
                sent_fc = payload[1]
                recv_fc = resp[1]
                if recv_fc == (sent_fc | 0x80):
                    logger.warning(
                        f"[Driver] 設備業務拒絕 (Modbus Exception): Slave={resp[0]} "
                        f"FC=0x{sent_fc:02X} Code={resp[2]}"
                    )
                    return False 

        return True

    async def read(self, payload: bytes) -> bytes:
        return await self._send_and_recv(payload)
