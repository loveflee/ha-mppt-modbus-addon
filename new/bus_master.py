# =============================================================================
# bus_master.py - V3.9 工業封存版 (Bugfix)
# 相容：HAManager V2.9、RobustAsyncTcpDriver V1.3、GenericAdapter V2.2
# 修復歷程：
#   V3.5 : 多設備 HA 路由 bug（單一 ha_manager → ha_managers dict）
#   V3.7 : decode 空 dict regression、版本號、failure log
#   V3.8 : time.monotonic() NTP 免疫、MAX_PENDING_WRITES OOM 防護
#          ack is False 嚴格判斷、raw_data is not None 嚴格判斷
#          encode_write 移至鎖外（最小化 bus_lock 持有時間）
#   V3.9 : [Critical] 修復 build_* 回傳 tuple 未解包導致 driver.read 崩潰。
#          [Critical] 修復 adapter.decode 缺少 context 參數導致 TypeError。
#          [Significant] 移除本地 DriverTimeoutError，改由 driver 匯入，修復歸因失效。
# =============================================================================

import asyncio
import heapq
import time
import logging

# 💡 [修復 3] 刪除本地定義，直接從底層驅動匯入，解決 Exception 雙胞胎身份錯亂
from driver import DriverTimeoutError

logger = logging.getLogger(__name__)

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
    工業級總線排程器 V3.9
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
            # 這裡不設 self._task = None，保留給 main.py await 清理使用
        logger.info("[BusMaster] 調度器已發出停止信號")

    async def submit_write(self, uid: int, key: str, value):
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
        async with self.write_lock:
            while self.pending_writes:
                k = next(iter(self.pending_writes))
                v = self.pending_writes.pop(k)
                if k[0] in self.adapters:  # 設備仍存活
                    if not self.pending_writes:
                        self.write_event.clear()
                    return (k[0], k[1], v)
            self.write_event.clear()
            return None

    async def _arbitration_loop(self):
        while self.running:
            try:
                while self.slow_heap and self.slow_heap[0][1] not in self.adapters:
                    heapq.heappop(self.slow_heap)

                now = time.monotonic()
                next_poll_time = self.slow_heap[0][0] if self.slow_heap else now + 60
                sleep_time = max(0.0, next_poll_time - now)

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
                logger.info("[BusMaster] 調度迴圈已被安全取消")
                break
            except Exception:
                logger.exception("[BusMaster] 核心迴圈未預期例外，5s 後重試")
                await asyncio.sleep(5)

    # =========================================================================
    # 快車道：原子化寫入
    # =========================================================================

    async def _process_write(self, task):
        uid, key, value = task
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return

        physical_fault_count = 0

        for attempt in range(1, 4):
            raw_data = None
            read_context = None

            # 鎖外：CPU 運算
            try:
                write_payload = adapter.encode_write(key, value)
                # 💡 [修復 1] 解包 tuple，分離 bytes 與 context
                read_cmd_bytes, read_context = adapter.build_verify_read(key)
            except Exception:
                logger.exception(f"[{uid}] adapter 編碼失敗，跳過此次寫入")
                return

            # --- 臨界區：只做純 RS485 物理通訊 ---
            try:
                async with self.bus_lock:
                    ack = await self.driver.write(write_payload)

                    if ack is False:
                        logger.warning(f"[{uid}] 設備邏輯拒絕 key={key}，不重試")
                        self._record_success(uid)
                        return

                    # 💡 [修復 1] 確保只把 bytes 傳給 driver
                    raw_data = await self.driver.read(read_cmd_bytes)

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

            # 鎖外：CPU 解碼與驗證
            if raw_data is not None:
                try:
                    # 💡 [修復 2] 帶入解包出來的 read_context
                    decoded = adapter.decode(raw_data, read_context)

                    if not isinstance(decoded, dict) or not decoded:
                        raise DataDecodeError(f"Adapter 解碼無效: 預期非空 dict，收到 {type(decoded)}")

                    if _values_equal(decoded.get(key), value):
                        ha_mgr.publish_state(decoded)
                        self._record_success(uid)
                        logger.info(f"[{uid}] 寫入驗證成功 {key}={value}")
                        return
                    else:
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
        if not self.slow_heap:
            return

        _, uid = heapq.heappop(self.slow_heap)
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return

        raw_data = None
        poll_context = None

        # 鎖外：CPU 運算
        try:
            # 💡 [修復 1] 解包 tuple，分離 bytes 與 context
            read_cmd_bytes, poll_context = adapter.build_poll_read()
        except Exception:
            logger.exception(f"[{uid}] adapter build_poll_read 失敗")
            self._reschedule(uid)
            return

        # --- 臨界區 ---
        try:
            async with self.bus_lock:
                # 💡 [修復 1] 確保只把 bytes 傳給 driver
                raw_data = await self.driver.read(read_cmd_bytes)
        except (DriverTimeoutError, asyncio.TimeoutError):
            self._record_failure(uid)
        except Exception:
            logger.exception(f"[{uid}] 輪詢臨界區未預期例外")
            self._record_failure(uid)
        # --- 臨界區結束 ---

        if raw_data is not None:
            try:
                # 💡 [修復 2] 帶入解包出來的 poll_context
                decoded = adapter.decode(raw_data, poll_context)

                if not isinstance(decoded, dict) or not decoded:
                    raise DataDecodeError(f"Adapter 解碼無效: 預期非空 dict，收到 {type(decoded)}")

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
        state = self.device_states.get(uid)
        if state:
            interval = 60 if not state["online"] else state["interval"]
            heapq.heappush(self.slow_heap, (time.monotonic() + interval, uid))

    # =========================================================================
    # 狀態管理
    # =========================================================================

    def _record_failure(self, uid: int):
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
