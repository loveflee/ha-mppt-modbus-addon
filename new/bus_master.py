# =============================================================================
# bus_master.py - V3.6 工業封存版
# 相容：HAManager V2.8、RobustMQTTClient V1.5
# 修復：類別縮排錯誤、__name__ 語法錯誤
# 特性：多設備獨立 HA 路由、快慢車道、異常三分流、OOM 免疫、全局防崩潰
# =============================================================================

import asyncio
import heapq
import time
import logging

# 修正 1：Python 內建變數 __name__
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
    整數/字串精確比較，浮點用容差
    避免 decode 精度損失（如 50.1 vs 50.099998）導致永遠不等 → 無限重試
    """
    if isinstance(a, (int, str)) and isinstance(b, (int, str)):
        return a == b
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False

# Adapter 必要介面（register_device 驗證用）
_ADAPTER_REQUIRED = ("encode_write", "build_verify_read", "build_poll_read", "decode")


# 修正 2：全類別正確縮排
class BusMasterScheduler:
    """
    工業級總線排程器 V3.6
    多設備路由：每個 uid 綁定自己的 HAManager 實例，狀態各自發布不串台
    快慢車道：覆蓋型 Dict 快車道（OOM 免疫）+ Heap 慢車道（精確到期）
    防餓死：快車道連跑 5 次讓慢車道優先
    """

    def __init__(self, driver):
        """
        Args:
            driver : 底層通訊驅動，需提供 await write(payload) / await read(cmd)
                     write() 返回 True/False 或拋 DriverTimeoutError
                     read()  返回 bytes 或拋 DriverTimeoutError
        """
        self.driver = driver

        self.adapters = {}      # {uid: adapter}
        self.ha_managers = {}   # {uid: HAManager} — 一對一路由，避免多設備串台
        self.device_states = {} # {uid: {...}}

        # 覆蓋型快車道：同 (uid, key) 只保留最新值，天然免疫 OOM 與命令積壓
        self.pending_writes = {}
        self.write_event = asyncio.Event()
        self.write_lock = asyncio.Lock()

        self.slow_heap = []            # [(到期時間, uid), ...]
        self.bus_lock = asyncio.Lock() # RS485 實體總線互斥鎖

        self.running = False
        self.consecutive_fast = 0
        self._task = None

    # =========================================================================
    # 設備管理
    # =========================================================================

    def register_device(self, uid: int, adapter, ha_manager, poll_interval: int = 10):
        """
        註冊設備
        驗證 uid 與 adapter 介面，確保後續排程不因缺失方法崩潰
        ha_manager 一對一綁定，確保狀態路由正確
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
        heapq.heappush(self.slow_heap, (time.time(), uid))
        logger.info(f"[BusMaster] 設備 #{uid} 已註冊，輪詢間隔 {poll_interval}s")

    def unregister_device(self, uid: int):
        """
        動態註銷設備
        清理 adapters / ha_managers / device_states
        slow_heap 殘留條目由 _arbitration_loop 在彈出時自動跳過
        """
        if uid not in self.adapters:
            logger.warning(f"[BusMaster] 設備 #{uid} 不存在，無法註銷")
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
        推入寫入任務（外部呼叫）
        同 uid+key 自動覆蓋舊值，無論 MQTT 湧入幾千次相同命令，
        記憶體中永遠只有最新一筆
        """
        if uid not in self.adapters:
            logger.warning(f"[BusMaster] 寫入目標 #{uid} 未註冊，丟棄")
            return
        async with self.write_lock:
            self.pending_writes[(uid, key)] = value
        self.write_event.set()

    # =========================================================================
    # 調度核心
    # =========================================================================

    async def _get_next_write_task(self):
        """取出一個寫入任務；next(iter()) 相容普通 dict，不需要 OrderedDict"""
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
        完美掛起：無任務時 wait_for 掛起，零 CPU 消耗
        heap 垃圾清理：每輪清理頂部已註銷的 uid
        全局例外防護：任何未預期例外不殺死 Task，5s 後繼續
        """
        while self.running:
            try:
                # heap 垃圾清理：跳過已 unregister 的設備
                while self.slow_heap and self.slow_heap[0][1] not in self.adapters:
                    heapq.heappop(self.slow_heap)

                now = time.time()
                next_poll_time = self.slow_heap[0][0] if self.slow_heap else now + 60
                sleep_time = max(0.0, next_poll_time - now)

                # 防餓死：快車道連跑 5 次且慢車道已到期，強制讓道
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
                    # 完美掛起：等待快車道喚醒或慢車道到期
                    await asyncio.wait_for(self.write_event.wait(), timeout=sleep_time)
                except asyncio.TimeoutError:
                    await self._process_poll()
                    self.consecutive_fast = 0

            except asyncio.CancelledError:
                logger.info("[BusMaster] 調度器收到停止信號")
                break
            except Exception:
                # 全局防護：捕獲所有未預期例外，Task 絕對不死
                logger.exception("[BusMaster] 核心迴圈未預期例外，5s 後重試")
                await asyncio.sleep(5)

    # =========================================================================
    # 快車道：原子化寫入
    # =========================================================================

    async def _process_write(self, task):
        """
        原子化寫入：write → read_back → verify
        計數器設計（非旗標）：
          physical_fault_count 只計 Timeout / CRC / 未預期例外
          值不符（硬體 clamp）不累積，確保 last-write-wins 不覆蓋正確歸因
          3 次後：physical_fault_count >= 2 → 懲罰；否則設備存活
        """
        uid, key, value = task
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return  

        physical_fault_count = 0

        for attempt in range(1, 4):
            raw_data = None

            # --- 臨界區：只做 RS485 物理通訊，最小化鎖持有時間 ---
            try:
                async with self.bus_lock:
                    write_payload = adapter.encode_write(key, value)
                    ack = await self.driver.write(write_payload)

                    if not ack:
                        # 設備邏輯拒絕（Modbus Exception 等）
                        logger.warning(f"[{uid}] 設備邏輯拒絕 key={key}，不重試")
                        self._record_success(uid)
                        return

                    read_cmd = adapter.build_verify_read(key)
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
            # --- 臨界區結束，鎖已釋放 ---

            # 鎖外：CPU 解碼與驗證
            if raw_data:
                try:
                    decoded = adapter.decode(raw_data)
                    if not decoded:
                        raise DataDecodeError("empty payload")

                    if _values_equal(decoded.get(key), value):
                        ha_mgr.publish_state(decoded)
                        self._record_success(uid)
                        logger.info(f"[{uid}] 寫入驗證成功 {key}={value}")
                        return

                    else:
                        # 硬體 clamp/ramp：設備接受命令但輸出受限，設備仍活著
                        logger.warning(
                            f"[{uid}] 回讀值不符 key={key} "
                            f"寫入={value} 回讀={decoded.get(key)} (嘗試 {attempt}/3)"
                        )

                except DataDecodeError as e:
                    # CRC 錯誤 = EMI 干擾 = 物理異常
                    logger.warning(f"[{uid}] CRC/解析失敗: {e} (嘗試 {attempt}/3)")
                    physical_fault_count += 1
                except Exception:
                    logger.exception(f"[{uid}] 解碼未預期例外 (嘗試 {attempt}/3)")
                    physical_fault_count += 1

            await asyncio.sleep(0.5)

        # 3 次耗盡後，依計數器歸因
        if physical_fault_count >= 2:
            logger.error(f"[{uid}] 寫入耗盡，主因物理異常 ({physical_fault_count}/3)")
            self._record_failure(uid)
        else:
            # 主因為值不符（硬體限制），設備存活
            logger.error(f"[{uid}] 寫入耗盡，回讀值不符（硬體限制？），設備維持 ONLINE")
            self._record_success(uid)

    # =========================================================================
    # 慢車道：常規輪詢
    # =========================================================================

    async def _process_poll(self):
        """慢車道：讀取設備狀態並發布，離線時降速探測"""
        if not self.slow_heap:
            return

        _, uid = heapq.heappop(self.slow_heap)
        adapter = self.adapters.get(uid)
        ha_mgr = self.ha_managers.get(uid)
        if not adapter or not ha_mgr:
            return

        raw_data = None

        # --- 臨界區 ---
        try:
            async with self.bus_lock:
                read_cmd = adapter.build_poll_read()
                raw_data = await self.driver.read(read_cmd)
        except (DriverTimeoutError, asyncio.TimeoutError):
            self._record_failure(uid)
        except Exception:
            logger.exception(f"[{uid}] 輪詢臨界區未預期例外")
            self._record_failure(uid)
        # --- 臨界區結束 ---

        if raw_data:
            try:
                decoded = adapter.decode(raw_data)
                if decoded:
                    ha_mgr.publish_state(decoded)
                    self._record_success(uid)
                else:
                    raise DataDecodeError("decode returned None")
            except DataDecodeError:
                self._record_failure(uid)
            except Exception:
                logger.exception(f"[{uid}] 輪詢解碼未預期例外")
                self._record_failure(uid)

        # 推回 heap：離線時 60s 降速探測，正常時按設定間隔
        state = self.device_states.get(uid)
        if state:
            interval = 60 if not state["online"] else state["interval"]
            heapq.heappush(self.slow_heap, (time.time() + interval, uid))

    # =========================================================================
    # 狀態管理
    # =========================================================================

    def _record_failure(self, uid: int):
        """物理異常累積；達 5 次判定 OFFLINE，自動進入 60s 降速探測"""
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
        """重置計數；防抖：連續 2 次成功才宣告 ONLINE，防 HA 介面狂閃"""
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
