# =============================================================================
# bus_master.py - V3.2 工業封存版
# 修復：value mismatch 誤殺（硬體 clamp 不是斷線）、浮點比較精度問題
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
    """CRC 錯誤或封包長度異常（視同物理干擾）"""
    pass


def _values_equal(a, b, tolerance: float = 0.01) -> bool:
    """
    浮點安全比較
    整數/字串用精確比較，浮點用容差比較
    避免 decode 精度損失導致永遠不等
    """
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= tolerance
        except (TypeError, ValueError):
            return False
    return a == b


class BusMasterScheduler:
    """
    工業級總線排程器 V3.2

    快慢車道分離：覆蓋型 Dict 快車道 + Heap 慢車道
    異常三分流：
      物理 Timeout/CRC → 累積斷線懲罰
      設備邏輯拒絕（ack=False）→ 設備存活，不懲罰
      硬體 clamp/值不符 → 設備存活，記錄警告，不懲罰
    """

    def __init__(self, driver, ha_manager):
        self.driver = driver
        self.ha_manager = ha_manager

        self.adapters = {}
        self.device_states = {}

        # 覆蓋型快車道：同 (uid, key) 只保留最新值，免疫 OOM 與命令積壓
        self.pending_writes = {}
        self.write_event = asyncio.Event()
        self.write_lock = asyncio.Lock()

        self.slow_heap = []
        self.bus_lock = asyncio.Lock()  # RS485 實體總線互斥鎖

        self.running = False
        self.consecutive_fast = 0
        self._task = None

    def register_device(self, uid: int, adapter, poll_interval: int = 10):
        """註冊設備，初始化狀態表與慢車道排程"""
        self.adapters[uid] = adapter
        self.device_states[uid] = {
            "timeout_count": 0,
            "success_count": 0,
            "online": False,
            "interval": poll_interval,
        }
        heapq.heappush(self.slow_heap, (time.time(), uid))
        logger.info(f"[BusMaster] 設備 #{uid} 已註冊，輪詢間隔 {poll_interval}s")

    async def submit_write(self, uid: int, key: str, value):
        """外部呼叫：推入寫入任務，同 uid+key 自動覆蓋舊值"""
        if uid not in self.adapters:
            return
        async with self.write_lock:
            self.pending_writes[(uid, key)] = value
        self.write_event.set()

    def start(self):
        self.running = True
        self._task = asyncio.create_task(self._arbitration_loop())

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    # =========================================================================
    # 調度核心
    # =========================================================================

    async def _get_next_write_task(self):
        """取出一個寫入任務（FIFO），字典清空時重置 Event"""
        async with self.write_lock:
            if not self.pending_writes:
                self.write_event.clear()
                return None
            k = next(iter(self.pending_writes))
            v = self.pending_writes.pop(k)
            if not self.pending_writes:
                self.write_event.clear()
            return (k[0], k[1], v)

    async def _arbitration_loop(self):
        """
        核心調度迴圈

        完美掛起：無任務時 wait_for 掛起直到快車道喚醒或慢車道到期
        防餓死：快車道連跑 5 次且慢車道已到期，強制執行輪詢
        """
        while self.running:
            now = time.time()
            next_poll_time = self.slow_heap[0][0] if self.slow_heap else now + 60
            sleep_time = max(0.0, next_poll_time - now)

            # 防餓死：快車道讓道給慢車道
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
                break

    # =========================================================================
    # 快車道：原子化寫入
    # =========================================================================

    async def _process_write(self, task):
        """
        原子化寫入：write → read_back → verify

        異常三分流（重要）：
          DriverTimeoutError / DataDecodeError → 物理異常 → _record_failure
          ack = False → 設備邏輯拒絕 → 立即 return，_record_success（設備活著）
          值不符（硬體 clamp/ramp）→ 設備活著 → 3 次後 _record_success，記錄警告
        """
        uid, key, value = task
        adapter = self.adapters[uid]
        physical_fault_count = 0  # 計數器，防止 last-write-wins 旗標被蓋掉

        for attempt in range(1, 4):
            raw_data = None

            # --- 臨界區：只做 RS485 物理通訊 ---
            try:
                async with self.bus_lock:
                    write_payload = adapter.encode_write(key, value)
                    ack = await self.driver.write(write_payload)

                    if not ack:
                        # 設備邏輯拒絕（Modbus Exception 0x02/0x03 等）
                        # 設備有回應 = 設備活著，不重試（重試不會讓設備改變限制）
                        logger.warning(f"[{uid}] 設備邏輯拒絕 key={key}，不重試")
                        self._record_success(uid)
                        return

                    read_cmd = adapter.build_verify_read(key)
                    raw_data = await self.driver.read(read_cmd)

            except (DriverTimeoutError, asyncio.TimeoutError):
                logger.warning(f"[{uid}] 物理 Timeout (嘗試 {attempt}/3)")
                physical_fault_count += 1
                await asyncio.sleep(0.5)  # 給總線喘息
                continue
            # --- 臨界區結束 ---

            # 鎖外：CPU 解碼與狀態發布
            if raw_data:
                try:
                    decoded = adapter.decode(raw_data)
                    if not decoded:
                        raise DataDecodeError("empty payload")

                    if _values_equal(decoded.get(key), value):
                        # 寫入驗證成功
                        self.ha_manager.publish_state(decoded)
                        self._record_success(uid)
                        logger.info(f"[{uid}] 寫入驗證成功 {key}={value}")
                        return

                    else:
                        # 回讀值不符：可能是硬體 clamp/ramp，設備仍然活著
                        # 不歸類為物理故障，不累積 physical_fault_count
                        logger.warning(
                            f"[{uid}] 回讀值不符 key={key} "
                            f"寫入={value} 回讀={decoded.get(key)} "
                            f"(嘗試 {attempt}/3)"
                        )

                except DataDecodeError as e:
                    # CRC 錯誤 = 物理干擾
                    logger.warning(f"[{uid}] CRC/解析失敗: {e} (嘗試 {attempt}/3)")
                    physical_fault_count += 1

            await asyncio.sleep(0.5)

        # 3 次耗盡後依計數器歸因
        if physical_fault_count >= 2:
            # Timeout 或 CRC 為主因 → 物理斷線懲罰
            logger.error(f"[{uid}] 寫入耗盡，主因物理異常 ({physical_fault_count}/3次)")
            self._record_failure(uid)
        else:
            # 值不符為主因（硬體 clamp/設備限制）→ 設備活著，不懲罰
            logger.error(
                f"[{uid}] 寫入耗盡，回讀值始終不符（硬體限制？），設備維持 ONLINE"
            )
            self._record_success(uid)

    # =========================================================================
    # 慢車道：常規輪詢
    # =========================================================================

    async def _process_poll(self):
        """慢車道輪詢：讀取設備狀態並發布"""
        if not self.slow_heap:
            return

        _, uid = heapq.heappop(self.slow_heap)
        adapter = self.adapters[uid]
        raw_data = None

        # --- 臨界區 ---
        try:
            async with self.bus_lock:
                read_cmd = adapter.build_poll_read()
                raw_data = await self.driver.read(read_cmd)
        except (DriverTimeoutError, asyncio.TimeoutError):
            self._record_failure(uid)
        # --- 臨界區結束 ---

        if raw_data:
            try:
                decoded = adapter.decode(raw_data)
                if decoded:
                    self.ha_manager.publish_state(decoded)
                    self._record_success(uid)
                else:
                    raise DataDecodeError("decode returned None")
            except DataDecodeError:
                self._record_failure(uid)

        # 離線時降速探測，正常時按設定間隔
        state = self.device_states[uid]
        interval = 60 if not state["online"] else state["interval"]
        heapq.heappush(self.slow_heap, (time.time() + interval, uid))

    # =========================================================================
    # 狀態管理
    # =========================================================================

    def _record_failure(self, uid: int):
        """物理異常累積；達 5 次判定 OFFLINE，降速探測"""
        state = self.device_states[uid]
        state["timeout_count"] += 1
        state["success_count"] = 0
        logger.error(f"[{uid}] 通訊失敗，累計 {state['timeout_count']} 次")

        if state["timeout_count"] >= 5 and state["online"]:
            state["online"] = False
            self.ha_manager.set_availability(False)
            logger.critical(f"[{uid}] 判定 OFFLINE，60s 慢速探測")

    def _record_success(self, uid: int):
        """重置計數；防抖：連續 2 次成功才宣告 ONLINE，防 UI 狂閃"""
        state = self.device_states[uid]
        state["timeout_count"] = 0
        state["success_count"] += 1

        if not state["online"] and state["success_count"] >= 2:
            state["online"] = True
            self.ha_manager.set_availability(True)
            logger.info(f"[{uid}] 連續通訊成功，恢復 ONLINE")
