# =============================================================================
# driver.py - V1.4 工業封存版 (觀測升級)
# 相容：BusMaster V3.8+、ModbusTcpDriver V1.0+
# 修復歷程：
# V1.1 : TCP 假死重連、flush 上限、connect timeout、FC 誤殺防護
# V1.3 : 短連線串口伺服器抗性、time.monotonic() NTP 免疫、_io_lock 死鎖修復
# V1.4 : [Feature] 新增 TX/RX 底層 Hex Dump 觀測點 (需將 config.yaml 設為 DEBUG)
# =============================================================================
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class DriverTimeoutError(Exception):
    """硬體層無回應或物理干擾，交由 Bus Master 處置"""
    pass

class RobustAsyncTcpDriver:
    """
    協議盲目 TCP→RS485 驅動層

    短連線抗性設計：
      廉價串口伺服器會主動踢閒置 TCP，timeout 視同死連線
      每次 timeout/斷線都強制重建 Socket，不依賴長連線假設

    死鎖防護：
      _disconnect_locked()：內部版，在已持有 _io_lock 時呼叫
      disconnect()：外部版，自己拿鎖再呼叫內部版
      _reconnect_locked()：在鎖內執行，sleep 在鎖外（由呼叫方負責）
    """

    def __init__(self, host: str, port: int,
                 timeout: float = 1.0,
                 inter_frame_delay: float = 0.18,
                 connect_timeout: float = 5.0,
                 idle_timeout: float = 0.03,
                 max_response_bytes: int = 2048,
                 max_frame_time: float = 1.0,
                 flush_max_time: float = 0.05):
        """
        :param timeout:           等待設備第一筆回應（秒）
        :param inter_frame_delay: RS485 收發切換硬體極限（秒）
        :param connect_timeout:   TCP connect 上限，防 SYN 卡 2 分鐘（秒）
        :param idle_timeout:      碎包 Idle 判定（秒），30ms 夠用
        :param max_response_bytes:單次最大接收量，防 OOM 與雜訊攻擊
        :param max_frame_time:    整個 Frame 最大接收時間（秒），防滴漏攻擊
        :param flush_max_time:    flush 緩衝區最大時間（秒），防高頻雜訊卡死
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.inter_frame_delay = inter_frame_delay
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        self.max_response_bytes = max_response_bytes
        self.max_frame_time = max_frame_time
        self.flush_max_time = flush_max_time

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_comm_time: float = 0.0
        self._io_lock = asyncio.Lock()

    # =========================================================================
    # 連線管理
    # =========================================================================

    async def connect(self) -> bool:
        """建立 TCP 連線，加 connect_timeout 防 SYN 無回應凍結"""
        try:
            logger.info(f"[Driver] 連線 {self.host}:{self.port}")
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout
            )
            logger.info("[Driver] 連線成功")
            return True
        except asyncio.TimeoutError:
            logger.error(f"[Driver] 連線 Timeout ({self.connect_timeout}s)")
            return False
        except Exception:
            logger.exception("[Driver] 連線失敗")
            return False

    def _close_socket(self, writer):
        """同步關閉 socket，fire-and-forget，不 await（避免在鎖內長等）"""
        if writer:
            try:
                writer.close()
            except Exception:
                pass

    def _disconnect_locked(self):
        """內部斷線（在已持有 _io_lock 時呼叫）"""
        writer = self._writer
        self._reader = None
        self._writer = None
        self._close_socket(writer)

    async def disconnect(self):
        """外部安全斷線（在鎖外呼叫）"""
        async with self._io_lock:
            self._disconnect_locked()
        logger.info("[Driver] 已斷線")

    async def _reconnect_locked(self):
        """內部重連（在已持有 _io_lock 時呼叫）"""
        self._disconnect_locked()
        success = await self.connect()
        if not success:
            raise DriverTimeoutError("TCP 重連失敗，下次排程繼續重試")
        logger.info("[Driver] 重連成功")

    # =========================================================================
    # 底層 I/O
    # =========================================================================

    async def _flush_buffer(self):
        """清除殘留雜訊"""
        if not self._reader:
            return
        flushed = 0
        deadline = time.monotonic() + self.flush_max_time
        try:
            while flushed < self.max_response_bytes:
                if time.monotonic() > deadline:
                    logger.warning(f"[Driver] Flush 超時 ({self.flush_max_time}s)，強制中斷")
                    break
                chunk = await asyncio.wait_for(self._reader.read(1024), timeout=0.01)
                if not chunk:
                    break
                flushed += len(chunk)
                logger.debug(f"[Driver] 丟棄殘留 {len(chunk)}B")
        except asyncio.TimeoutError:
            pass  # 預期行為，buffer 已空
        except Exception as e:
            logger.debug(f"[Driver] Flush 異常（可忽略）: {e}")

    async def _enforce_inter_frame_delay(self):
        """確保 RS485 收發切換有足夠硬體時間"""
        elapsed = time.monotonic() - self._last_comm_time
        if elapsed < self.inter_frame_delay:
            await asyncio.sleep(self.inter_frame_delay - elapsed)

    async def _send_and_recv(self, payload: bytes) -> bytes:
        """底層原子化盲發盲收"""
        async with self._io_lock:
            reader = self._reader
            writer = self._writer

            if not reader or not writer:
                await self._reconnect_locked()
                reader = self._reader
                writer = self._writer

            await self._enforce_inter_frame_delay()
            await self._flush_buffer()

            # 發送
            try:
                # 💡 [V1.4 新增] TX 觀測點
                logger.debug(f"[Driver] TX: {payload.hex(' ').upper()}")
                
                writer.write(payload)
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"[Driver] 發送失敗（TCP 斷線）: {e}")
                await self._reconnect_locked()
                raise DriverTimeoutError("發送失敗，已重連，下次重試")

            # 接收
            raw_response = bytearray()
            frame_deadline = time.monotonic() + self.max_frame_time

            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=self.timeout)
                if not chunk:
                    logger.warning("[Driver] 對端關閉連線（TCP FIN）")
                    await self._reconnect_locked()
                    raise DriverTimeoutError("對端關閉連線，已重連")
                raw_response.extend(chunk)

                while True:
                    if len(raw_response) >= self.max_response_bytes:
                        raise DriverTimeoutError("接收溢出，可能遭受雜訊攻擊")
                    if time.monotonic() > frame_deadline:
                        raise DriverTimeoutError("Frame 超時（滴漏攻擊防護）")
                    try:
                        chunk = await asyncio.wait_for(
                            reader.read(1024), timeout=self.idle_timeout
                        )
                        if not chunk:
                            break
                        raw_response.extend(chunk)
                    except asyncio.TimeoutError:
                        break  # Idle 到期，Frame 收完

            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning(f"[Driver] 接收失敗（TCP 斷線）: {e}")
                await self._reconnect_locked()
                raise DriverTimeoutError("接收失敗，已重連，下次重試")

            except asyncio.TimeoutError:
                logger.warning("[Driver] 設備無回應（Timeout），強制重置 Socket")
                await self._reconnect_locked()
                raise DriverTimeoutError("無回應，已清洗 Socket，下次重試")

        self._last_comm_time = time.monotonic()
        
        # 💡 [V1.4 新增] RX 觀測點
        logger.debug(f"[Driver] RX: {bytes(raw_response).hex(' ').upper()}")
        
        return bytes(raw_response)

    # =========================================================================
    # Bus Master 介面合約
    # =========================================================================

    async def write(self, payload: bytes) -> bool:
        """Modbus Exception 精確判定"""
        resp = await self._send_and_recv(payload)

        if (len(resp) == 5 and len(payload) >= 2
                and resp[0] == payload[0]
                and 1 <= resp[2] <= 4):
            sent_fc = payload[1]
            recv_fc = resp[1]
            if recv_fc == (sent_fc | 0x80):
                logger.warning(
                    f"[Driver] Modbus Exception: Slave={resp[0]} "
                    f"FC=0x{sent_fc:02X} Code={resp[2]}"
                )
                return False

        return True

    async def read(self, payload: bytes) -> bytes:
        """協議盲目：回傳 Raw Bytes，解碼由 Adapter 負責"""
        return await self._send_and_recv(payload)
