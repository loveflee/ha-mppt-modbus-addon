# =============================================================================
# bus_master.py - V3.8 工業封存版
# 相容：HAManager V2.7、RobustAsyncTcpDriver V1.1
# 修復歷程：
#   V3.5 : 多設備 HA 路由 bug（單一 ha_manager → ha_managers dict）
#   V3.7 : decode 空 dict regression、版本號、failure log
#   V3.8 : time.monotonic() NTP 免疫、MAX_PENDING_WRITES OOM 防護
#          ack is False 嚴格判斷、raw_data is not None 嚴格判斷
#          encode_write 移至鎖外（最小化 bus_lock 持有時間）
# =============================================================================

import asyncio
import heapq
import time
import logging

logger = logging.getLogger(__name__)


class DriverTimeoutError(Exception):
    """硬體層無回應或物理干擾"""
    pass


class DataDecodeError(Exception):
    """CRC 錯誤、封包長度異常或解碼型別錯誤"""
    pass


def _values_equal(a, b, tolerance: float = 0.01) -> bool:
    """
    浮點安全比較

    同型別整數/字串精確比較，其餘用容差
    type() 而非 isinstance()：避免 bool/int 子類混淆
    """
    if type(a) == type(b) and isinstance(a, (int, str)):
        return a == b
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


_ADAPTER_REQUIRED = ("encode_write", "build_verify_read", "build_poll_read", "decode")


class BusMasterScheduler:
    """
    工業級總線排程器 V3.8

    多設備路由：每個 uid 綁定自己的 HAManager，狀態不串台
    時鐘免疫：全面使用 time.monotonic()，NTP 校時不影響排程
    OOM 防護：MAX_PENDING_WRITES 硬上限，惡意 MQTT 洪泛無法爆記憶體
    鎖最小化：encode/decode CPU 運算在 bus_lock 外執行
    異常三分流：物理故障 / 邏輯拒絕 / 硬體 clamp 精確歸因
    """

    MAX_PENDING_WRITES = 200  # MQTT 洪泛防護硬上限

    def __init__(self, driver):
        self.driver = driver
        self.adapters = {}
        self.ha_managers = {}
        self.device_states = {}

        self.pending_writes = {}
        self.write_event = asyncio.Event()
        self.write_lock = asyncio.Lock()

        self.slow_heap = []
        self.bus_lock = asyncio.Lock()  # RS485 實體總線互斥鎖

        self.running = False
        self.consecutive_fast = 0
        self._task = None

    # =========================================================================
    # 設備管理
    # =========================================================================

    def register_device(self, uid: int, adapter, ha_manager, poll_interval: int = 10):
        """
        註冊設備，驗證 adapter 介面完整性

        Args:
            uid          : 設備 Modbus Address（正整數）
            adapter      : 設備地圖 + 編解碼器
            ha_manager   : 此設備專屬的 HAManager 實例
            poll_interval: 正常輪詢間隔（秒）
        """
        if not isinstance(uid, int) or uid <= 0:
            logger.error(f"[BusMaster] 無效 UID: {uid}，必須為正整數")
            return
        for method in _ADAPTER_REQUIRED:
            if not hasattr(adapter, method):
                logger.error(f"[BusMaster] 設備 #{uid} adapter 缺少 {method}()，註冊失敗")
                return

        self.adapters[uid] = adapter
        self.ha_managers[uid] = ha_manager
        self.device_states[uid] = {
            "timeout_count": 0,
            "success_count": 0,
            "online": False,
            "interval": poll_interval,
        }
        heapq.heappush(self.slow_heap, (time.monotonic(), uid))
        logger.info(f"[BusMaster] 設備 #{uid} 已註冊，輪詢間隔 {poll_interval}s")

    def unregister_device(self, uid: int):
        """
        動態註銷設備

        slow_heap 與 pending_writes 殘留條目由調度迴圈懶刪除，
        無需在此加鎖清理（避免同步函數操作異步鎖導致死鎖）
        """
        if uid not in self.adapters:
            return
        del self.adapters[uid]
        del self.ha_managers[uid]
        del self.device_states[uid]
        logger.info(f"[BusMaster] 設備 #{uid} 已註銷")

    # =========================================================================
    # 啟動/停止
    # =========================================================================

    def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._arbitration_loop())
        logger.info("[BusMaster] 調度器已啟動")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[BusMaster] 調度器已停止")

    async def submit_write(self, uid: int, key: str, value):
        """
        推入寫入任務，同 uid+key 自動覆蓋舊值

        OOM 防護：達上限時只允許覆蓋現有 key，拒絕新 key
        """
        if uid not in self.adapters:
            return
        async with self.write_lock:
            if (len(self.pending_writes) >= self.MAX_PENDING_WRITES
                    and (uid, key) not in self.pending_writes):
                logger.error(
                    f"[BusMaster] pending_writes 達上限 {self.MAX_PENDING_WRITES}，"
                    f"丟棄新 key uid={uid} key={key}"
                )
                return
            self.pending_writes[(uid, key)] = value
        self.write_event.set()

    # =========================================================================
    # 調度核心
    # =========================================================================

    async def _get_next_write_task(self):
        """
        取出一個寫入任務

        懶刪除：順手跳過已 unregister 的設備殘留條目
        Python 3.7+ dict 保持插入順序，next(iter()) 即 FIFO
        """
        async with self.write_lock:
            while self.pending_writes:
                k = next(iter(self.pending_writes))
                v = self.pending_writes.pop(k)
                if k[0] in self.adapters:  # 設備仍存活
                    if not self.pending_writes:
                        self.write_event.clear()
                    return (k[0], k[1], v)
            # 字典空了或全是殘留垃圾
            self.write_event.clear()
            return None

    async def _arbitration_loop(self):
        """
        核心調度迴圈

        time.monotonic() 免疫 NTP 校時，不會因系統時間跳變導致排程睡死
        heap 懶刪除：O(1) 攤銷，比 heapify() O(N) 更高效
        全局 except 防護：任何未預期例外不殺死 Task
        """
        while self.running:
            try:
                # heap 懶刪除：彈出已 unregister 的設備
                while self.slow_heap and self.slow_heap[0][1] not in self.adapters:
                    heapq.heappop(self.slow_heap)

                now = time.monotonic()
                next_poll_time = self.slow_heap[0][0] if self.slow_heap else now + 60
                sleep_time = max(0.0, next_poll_time - now)

                # 防餓死：快車道連跑 5 次讓慢車道優先
                if self.consecutive_fast >= 5 and sleep_time <= 0:
                    await self._process_poll()
                    self.consecutive_fast = 0
                    continue

                write_task = await self._get_next_write_task()
                if write_task:
                    await self._process_write(write_task)
                    self.consecutive_fast += 1
                    continue

                try:
                    await asyncio.wait_for(self.write_event.wait(), timeout=sleep_time)
                except asyncio.TimeoutError:
                    await self._process_poll()
                    self.consecutive_fast = 0

            except asyncio.CancelledError:
                logger.info("[BusMaster] 調度器收到停止信號")
                break
            except Exception:
                logger.exception("[BusMaster] 核心迴圈未預期例外，5s 後重試")
                await asyncio.sleep(5)

    # =========================================================================
    # 快車道：原子化寫入
    # =========================================================================

    async def _process_write(self, task):
        """
        原子化寫入：encode → write → read → decode → verify

        鎖最小化：encode_write / build_verify_read（CPU 運算）在 bus_lock 外執行
        ack is False：只攔明確拒絕，兼容回傳 None / bytes 的 fire-and-forget driver
        raw_data is not None：兼容回傳 b"\\x00" 的合法零值封包
        physical_fault_count 計數器：防 last-write-wins 旗標被蓋掉
        """
        uid, key, value = task
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return  # 執行中被 unregister，自然消耗

        physical_fault_count = 0

        for attempt in range(1, 4):
            raw_data = None

            # 鎖外：CPU 運算，不佔用 RS485 總線時間
            try:
                write_payload = adapter.encode_write(key, value)
                read_cmd = adapter.build_verify_read(key)
            except Exception:
                logger.exception(f"[{uid}] adapter 編碼失敗，跳過此次寫入")
                return

            # --- 臨界區：只做純 RS485 物理通訊 ---
            try:
                async with self.bus_lock:
                    ack = await self.driver.write(write_payload)

                    if ack is False:
                        # 設備明確邏輯拒絕（Modbus Exception），不重試
                        logger.warning(f"[{uid}] 設備邏輯拒絕 key={key}，不重試")
                        self._record_success(uid)
                        return

                    raw_data = await self.driver.read(read_cmd)

            except (DriverTimeoutError, asyncio.TimeoutError):
                logger.warning(f"[{uid}] 物理 Timeout (嘗試 {attempt}/3)")
                physical_fault_count += 1
                await asyncio.sleep(0.5)
                continue
            except Exception:
                logger.exception(f"[{uid}] 臨界區未預期例外 (嘗試 {attempt}/3)")
                physical_fault_count += 1
                await asyncio.sleep(0.5)
                continue
            # --- 臨界區結束 ---

            # 鎖外：CPU 解碼與驗證，MQTT publish 在鎖外不拖垮總線
            if raw_data is not None:
                try:
                    decoded = adapter.decode(raw_data)

                    # 型別強制校驗：攔截 None / [] / "" / {} 等劣質 Adapter 回傳
                    if not isinstance(decoded, dict) or not decoded:
                        raise DataDecodeError(
                            f"Adapter 解碼無效: 預期非空 dict，收到 {type(decoded)}"
                        )

                    if _values_equal(decoded.get(key), value):
                        ha_mgr.publish_state(decoded)
                        self._record_success(uid)
                        logger.info(f"[{uid}] 寫入驗證成功 {key}={value}")
                        return

                    else:
                        # 硬體 clamp/ramp：設備活著，不累積物理故障計數
                        logger.warning(
                            f"[{uid}] 回讀值不符 key={key} "
                            f"寫入={value} 回讀={decoded.get(key)} (嘗試 {attempt}/3)"
                        )

                except DataDecodeError as e:
                    logger.warning(f"[{uid}] 解析失敗: {e} (嘗試 {attempt}/3)")
                    physical_fault_count += 1
                except Exception:
                    logger.exception(f"[{uid}] 解碼未預期例外 (嘗試 {attempt}/3)")
                    physical_fault_count += 1

            await asyncio.sleep(0.5)

        # 3 次耗盡後依計數器歸因（非旗標，last-write-wins 安全）
        if physical_fault_count >= 2:
            logger.error(f"[{uid}] 寫入耗盡，主因物理異常 ({physical_fault_count}/3)")
            self._record_failure(uid)
        else:
            logger.error(f"[{uid}] 寫入耗盡，回讀值不符（硬體限制），設備維持 ONLINE")
            self._record_success(uid)

    # =========================================================================
    # 慢車道：常規輪詢
    # =========================================================================

    async def _process_poll(self):
        """慢車道：讀取狀態並發布，離線降速探測"""
        if not self.slow_heap:
            return

        _, uid = heapq.heappop(self.slow_heap)
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return  # 已 unregister，不推回 heap

        raw_data = None

        # 鎖外：CPU 運算
        try:
            read_cmd = adapter.build_poll_read()
        except Exception:
            logger.exception(f"[{uid}] adapter build_poll_read 失敗")
            self._reschedule(uid)
            return

        # --- 臨界區 ---
        try:
            async with self.bus_lock:
                raw_data = await self.driver.read(read_cmd)
        except (DriverTimeoutError, asyncio.TimeoutError):
            self._record_failure(uid)
        except Exception:
            logger.exception(f"[{uid}] 輪詢臨界區未預期例外")
            self._record_failure(uid)
        # --- 臨界區結束 ---

        if raw_data is not None:
            try:
                decoded = adapter.decode(raw_data)

                if not isinstance(decoded, dict) or not decoded:
                    raise DataDecodeError(
                        f"Adapter 解碼無效: 預期非空 dict，收到 {type(decoded)}"
                    )

                ha_mgr.publish_state(decoded)
                self._record_success(uid)

            except DataDecodeError as e:
                logger.warning(f"[{uid}] 輪詢解析失敗: {e}")
                self._record_failure(uid)
            except Exception:
                logger.exception(f"[{uid}] 輪詢解碼未預期例外")
                self._record_failure(uid)

        self._reschedule(uid)

    def _reschedule(self, uid: int):
        """推回 heap，離線降速探測"""
        state = self.device_states.get(uid)
        if state:
            interval = 60 if not state["online"] else state["interval"]
            heapq.heappush(self.slow_heap, (time.monotonic() + interval, uid))

    # =========================================================================
    # 狀態管理
    # =========================================================================

    def _record_failure(self, uid: int):
        """物理異常累積；達 5 次判定 OFFLINE，60s 降速探測"""
        state = self.device_states.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not state or not ha_mgr:
            return

        state["timeout_count"] += 1
        state["success_count"] = 0
        logger.error(f"[{uid}] 通訊失敗，累計 {state['timeout_count']} 次")

        if state["timeout_count"] >= 5 and state["online"]:
            state["online"] = False
            ha_mgr.set_availability(False)
            logger.critical(f"[{uid}] 判定 OFFLINE，進入 60s 慢速探測")

    def _record_success(self, uid: int):
        """重置計數；防抖：連續 2 次成功才宣告 ONLINE"""
        state = self.device_states.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not state or not ha_mgr:
            return

        state["timeout_count"] = 0
        state["success_count"] += 1

        if not state["online"] and state["success_count"] >= 2:
            state["online"] = True
            ha_mgr.set_availability(True)
            logger.info(f"[{uid}] 連續通訊成功，恢復 ONLINE")
