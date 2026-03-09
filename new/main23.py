# main.py v1.6
# 模組名稱：Edge Gateway V3 主控樞紐 (The Controller)
# 版本狀態：V1.6 (工業量產封存版 - 終極工廠介面修復)
# 核心職責：
#   1. 生命週期管理：解析 config.yaml，初始化底層通訊與 MQTT 代理。
#   2. 跨執行緒橋接：使用 asyncio.Queue 零延遲且安全地轉發 Paho MQTT 控制指令。
#   3. 工廠模式掛載：依據設備地圖 (Profile) 動態實例化 Adapter 與 HAManager。
#   4. 健康觀測站：獨立 Task 聚合底層錯誤計數，定期廣播 Heartbeat。
#   5. 優雅關機：攔截 SIGTERM/SIGINT，安全釋放排程鎖定與 TCP Socket。
# 修復歷程 (V1.5 -> V1.6)：
#   - [Critical] 徹底解耦 Driver 工廠介面：移除硬編碼的 TCP 參數，
#                改用 kwargs 動態透傳 (drv_params)，完美相容未來的 LocalSerialDriver。
#   - [Feature] 將必填欄位驗證 (_require) 改為 per-type 動態檢查。
# 相容性矩陣 (Dependencies)：
#   - BusMaster Scheduler V3.9
#   - Robust Async TCP Driver V1.3
#   - Generic Modbus Adapter V2.2
#   - HA Manager V2.9
#   - Robust MQTT Client V1.8

import asyncio
import signal
import yaml
import importlib
import logging
import json
import sys
import time

from driver import RobustAsyncTcpDriver
from bus_master import BusMasterScheduler
from mqtt_client import RobustMQTTClient
from ha_manager import HAManager
from generic_adapter import GenericModbusAdapter
from modbus_tcp_driver import AsyncModbusTcpDriver
from modbus_tcp_adapter import ModbusTcpAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("Main")

# 💡 [架構預留] Driver 工廠：未來擴充 LocalSerialDriver 等只需在此註冊
DRIVER_FACTORY = {
    "tcp_serial": RobustAsyncTcpDriver,
    "modbus_tcp": AsyncModbusTcpDriver,  # 加這行
    #"local_serial": LocalSerialDriver,

}

ADAPTER_FACTORY = {
    "generic": GenericModbusAdapter,
    "modbus_tcp": ModbusTcpAdapter,      # 加這行
    #"jkbms":   JkBmsAdapter,
}

class EdgeGateway:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.running = False
        self.start_time = time.monotonic()

        self.driver = None
        self.bus_master: BusMasterScheduler | None = None
        self.mqtt_client: RobustMQTTClient | None = None
        self.ha_managers: dict[int, HAManager] = {}
        self.node_id = "edge_gw"

        self._cmd_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bg_tasks = []

    # =========================================================================
    # 設定與地圖載入
    # =========================================================================

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            logger.critical(f"無法讀取設定檔 {self.config_path}", exc_info=True)
            sys.exit(1)

    def _load_profile(self, profile_name: str) -> dict:
        try:
            with open(f"{profile_name}.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            pass
        try:
            mod = importlib.import_module(profile_name)
            return {k: getattr(mod, k) for k in dir(mod) if not k.startswith('_')}
        except ImportError:
            logger.critical(f"找不到地圖檔: {profile_name}.yaml 或 {profile_name}.py")
            sys.exit(1)

    @staticmethod
    def _require(cfg: dict, *keys: str):
        node = cfg
        path = []
        for k in keys:
            path.append(k)
            if not isinstance(node, dict) or k not in node:
                logger.critical(f"config.yaml 缺少必填欄位: {' → '.join(path)}")
                sys.exit(1)
            node = node[k]
        return node

    # =========================================================================
    # MQTT 回呼與橋接
    # =========================================================================

    def _on_mqtt_connected(self):
        logger.info("MQTT 上線，執行 Discovery 與訂閱...")
        cmd_topic = f"{self.node_id}/+/+/set/+"
        self.mqtt_client.subscribe(cmd_topic, qos=1)
        logger.info(f"已訂閱控制指令: {cmd_topic}")
        for ha_mgr in self.ha_managers.values():
            ha_mgr.publish_gateway_online()
            ha_mgr.send_discovery(cleanup=False)

    def _on_mqtt_message(self, msg):
        if self._loop is None or self._loop.is_closed():
            return

        def _put():
            try:
                self._cmd_queue.put_nowait(msg)
            except asyncio.QueueFull:
                logger.error(f"[MQTT Bridge] 指令 Queue 滿，丟棄 topic={msg.topic}")

        self._loop.call_soon_threadsafe(_put)

    async def _mqtt_consumer_task(self):
        logger.info("[MQTT Consumer] 已啟動")
        while self.running:
            try:
                msg = await asyncio.wait_for(self._cmd_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            topic_parts = msg.topic.split('/')
            if len(topic_parts) < 5 or topic_parts[3] != "set":
                continue

            uid_str = topic_parts[2]
            key = topic_parts[4]
            try:
                uid = int(uid_str)
            except ValueError:
                logger.warning(f"[Command] 無效 UID: {uid_str}")
                continue

            try:
                payload_str = msg.payload.decode('utf-8').strip()
            except Exception:
                logger.warning(f"[Command] payload 解碼失敗 topic={msg.topic}")
                continue

            logger.info(f"[Command] UID={uid} key={key} value={payload_str}")
            await self.bus_master.submit_write(uid, key, payload_str)

    # =========================================================================
    # Health Monitor
    # =========================================================================

    async def _health_monitor_task(self):
        logger.info("[Health Monitor] 已啟動")
        health_topic = f"{self.node_id}/health"

        while self.running:
            await asyncio.sleep(60)

            if not self.mqtt_client:
                continue

            devices_health = {}
            if self.bus_master:
                for uid, state in self.bus_master.device_states.items():
                    devices_health[str(uid)] = {
                        "online":        state.get("online", False),
                        "timeout_count": state.get("timeout_count", 0),
                        "success_count": state.get("success_count", 0),
                    }

            payload: dict = {
                "uptime_s":       int(time.monotonic() - self.start_time),
                "cmd_queue_size": self._cmd_queue.qsize(),
                "devices":        devices_health,
            }

            reconnect = getattr(self.driver, "reconnect_count", None)
            if reconnect is not None:
                payload["driver_reconnect_count"] = reconnect

            try:
                self.mqtt_client.publish(
                    health_topic,
                    json.dumps(payload),
                    qos=0,
                    retain=False,
                )
                logger.debug(f"[Health] {payload}")
            except Exception as e:
                logger.debug(f"[Health] 發布失敗: {e}")

    # =========================================================================
    # 生命週期 (Lifecycle)
    # =========================================================================

    async def start(self):
        cfg = self._load_config()
        sys_cfg = cfg.get("system", {})
        self.node_id = sys_cfg.get("node_id", "edge_gw_01")

        log_level = sys_cfg.get("log_level", "INFO").upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

        self._loop = asyncio.get_running_loop()

        # 1. 初始化通訊驅動 (Driver Factory - kwargs 透傳版)
        drv_cfg = cfg.get("driver", {})
        d_type = drv_cfg.get("type", "tcp_serial")
        DriverClass = DRIVER_FACTORY.get(d_type)
        
        if not DriverClass:
            logger.critical(f"啟動失敗：不支援的 Driver 類型 '{d_type}'")
            sys.exit(1)

        # 💡 [修復 1] 針對不同 type 進行特有的必填驗證，不綁死 host
        if d_type == "tcp_serial":
            self._require(drv_cfg, "host")
            self._require(drv_cfg, "port")
        elif d_type == "local_serial":
            self._require(drv_cfg, "port")
            self._require(drv_cfg, "baudrate")

        # 💡 [修復 2] 提取所有非 type 的參數，透過字典解包透傳 (kwargs) 給 Driver
        drv_params = {k: v for k, v in drv_cfg.items() if k != "type"}

        try:
            self.driver = DriverClass(**drv_params)
        except TypeError as e:
            logger.critical(f"啟動失敗：Driver 初始化參數錯誤 (請檢查 config.yaml 的 driver 區塊): {e}")
            sys.exit(1)

        await self.driver.connect()

        # 2. 初始化總線排程大腦
        self.bus_master = BusMasterScheduler(self.driver)

        # 3. 初始化 MQTT 與橋接邏輯
        mqtt_cfg = cfg.get("mqtt", {})
        discovery_prefix = mqtt_cfg.get("discovery_prefix", "homeassistant")
        self.mqtt_client = RobustMQTTClient(
            broker=self._require(mqtt_cfg, "broker"),
            port=mqtt_cfg.get("port", 1883),
            client_id=self.node_id,
            username=mqtt_cfg.get("username"),
            password=mqtt_cfg.get("password"),
        )
        lwt_topic = f"{self.node_id}/status"
        self.mqtt_client.set_lwt(lwt_topic, payload="offline", retain=True)
        self.mqtt_client.on_connected_callback = self._on_mqtt_connected

        _original_on_message = self.mqtt_client._on_message
        def _bridged_on_message(client, userdata, msg):
            _original_on_message(client, userdata, msg)
            self._on_mqtt_message(msg)
        self.mqtt_client.client.on_message = _bridged_on_message

        # 4. 執行設備掛載 (Device Mount)
        for dev in cfg.get("devices", []):
            uid = dev.get("uid")
            adapter_name = dev.get("adapter", "generic")
            profile_name = dev.get("profile")
            device_type = dev.get("device_type", "device")
            poll_interval = dev.get("poll_interval", 10)

            if not uid or not profile_name:
                logger.error(f"設備設定不完整，跳過: {dev}")
                continue

            AdapterClass = ADAPTER_FACTORY.get(adapter_name)
            if not AdapterClass:
                logger.error(f"跳過 UID={uid}: 找不到 Adapter '{adapter_name}'")
                continue

            profile_data = self._load_profile(profile_name)

            try:
                adapter = AdapterClass(uid, profile_data)
            except Exception:
                logger.exception(f"UID={uid} Adapter 實例化失敗，跳過")
                continue

            ha_mgr = HAManager(
                mqtt_client=self.mqtt_client,
                node_id=self.node_id,
                device_type=device_type,
                uid=uid,
                rmap=profile_data,
                discovery_prefix=discovery_prefix
            )
            self.ha_managers[uid] = ha_mgr

            self.bus_master.register_device(
                uid=uid,
                adapter=adapter,
                ha_manager=ha_mgr,
                poll_interval=poll_interval,
            )
            logger.info(f"✅ 設備已掛載: UID={uid} type={device_type} adapter={adapter_name}")

        # 5. 系統起飛
        self.running = True
        self.mqtt_client.connect()
        self.bus_master.start()
        
        self._bg_tasks = [
            asyncio.create_task(self._mqtt_consumer_task()),
            asyncio.create_task(self._health_monitor_task())
        ]

        logger.info("🚀 Edge Gateway V3 啟動完成")

        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """優雅關機：依序停止排程、廣播 offline、釋放連線"""
        if not self.running:
            return
        logger.info("執行優雅關機...")
        self.running = False

        if self.bus_master:
            self.bus_master.stop()
            if self.bus_master._task:
                try:
                    await self.bus_master._task
                except asyncio.CancelledError:
                    pass

        for t in self._bg_tasks:
            t.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)

        for ha_mgr in self.ha_managers.values():
            try:
                ha_mgr.publish_gateway_offline()
            except Exception:
                pass

        if self.mqtt_client:
            self.mqtt_client.disconnect()

        if self.driver:
            await self.driver.disconnect()

        logger.info("💤 系統已安全停止，記憶體/Task 已徹底清理")

# =============================================================================
# 程式進入點與訊號攔截
# =============================================================================

if __name__ == "__main__":
    gateway = EdgeGateway("config.yaml")

    def handle_signal(*args):
        logger.warning("收到終止訊號，開始優雅關機...")
        if gateway._loop and not gateway._loop.is_closed():
            gateway._loop.call_soon_threadsafe(
                gateway._loop.create_task, gateway.stop()
            )

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        pass
