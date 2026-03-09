# =============================================================================
# modbus_tcp_driver.py - V1.0
# 繼承自 RobustAsyncTcpDriver，專為原生 Modbus TCP 設備設計
#
# 改動點：
# 1. 拿掉 RTU 專屬的 Modbus Exception 偵測，交由 Adapter 處理 MBAP。
# 2. 其餘所有 Socket 管理、重連、OOM 防護、死鎖防禦，100% 繼承。
# =============================================================================

import logging
from driver import RobustAsyncTcpDriver, DriverTimeoutError

logger = logging.getLogger(__name__)

class AsyncModbusTcpDriver(RobustAsyncTcpDriver):
    """
    原生 Modbus TCP 驅動層
    不依賴 RS485，純走網路，無 CRC 驗證。
    """

    # __init__ 參數完全繼承父類，由 main.py 的 kwargs 透傳進來
    # 如果 config.yaml 沒有寫 port，這裡可以用 super().__init__ 給個預設值，
    # 但為了維持架構統一，我們讓 kwargs 直接決定一切。

    async def write(self, payload: bytes) -> bool:
        """
        Modbus TCP 寫入
        原生 TCP 的 Exception 判斷會看 MBAP Header，長度不是 5，
        所以直接盲發盲收，把解碼與 Exception 判定權力還給 Adapter。
        """
        try:
            # 盲發盲收
            await self._send_and_recv(payload)
            return True
        except DriverTimeoutError:
            # 斷線或 Timeout 往上拋，交給 BusMaster
            raise
        except Exception as e:
            logger.warning(f"[TCP Driver] 寫入未預期異常: {e}")
            raise DriverTimeoutError("寫入失敗，視同斷線")
    # read() 方法直接繼承父類，無需覆寫
