# =============================================================================

# main.py - Edge Gateway V3 主控樞紐 V1.2

# 相容：BusMaster V3.8、Driver V1.3、GenericAdapter V2.2

# HAManager V2.9、RobustMQTTClient（mqtt_client.py）

# 修復 V1.1 → V1.2：

# asyncio.get_event_loop() 在 **init** 抓到錯誤 loop

# → self._loop 改在 start() 用 asyncio.get_running_loop() 取得

# Health Monitor getattr 全回 0

# → 從 bus_master.device_states 聚合真實計數

# import json 移至頂層

# =============================================================================

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

logging.basicConfig(
level=logging.INFO,
format=’%(asctime)s [%(levelname)s] %(name)s: %(message)s’,
datefmt=’%Y-%m-%d %H:%M:%S’
)
logger = logging.getLogger(“Main”)

ADAPTER_FACTORY = {
“generic”: GenericModbusAdapter,
# “jkbms”:   JkBmsAdapter,
# “ampinvt”: AmpinvtAdapter,
}

class EdgeGateway:
def **init**(self, config_path: str = “config.yaml”):
self.config_path = config_path
self.running = False
self.start_time = time.monotonic()

```
    self.driver: RobustAsyncTcpDriver | None = None
    self.bus_master: BusMasterScheduler | None = None
    self.mqtt_client: RobustMQTTClient | None = None
    self.ha_managers: dict[int, HAManager] = {}
    self.node_id = "edge_gw"

    self._cmd_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    # _loop 不在 __init__ 抓：
    #   asyncio.run() 建立全新 loop，__init__ 裡 get_event_loop() 是不同物件
    #   在 start()（coroutine 內）用 get_running_loop() 才能拿到正確的 loop
    self._loop: asyncio.AbstractEventLoop | None = None

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
    """優先 .yaml，其次 import Python 模組（相容舊版 mppt_map_tw.py）"""
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
    """必填欄位驗證，找不到時給出明確錯誤而非 KeyError traceback"""
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
    """MQTT 連線/重連成功時觸發（在 paho 執行緒內執行）"""
    logger.info("MQTT 上線，執行 Discovery 與訂閱...")
    cmd_topic = f"{self.node_id}/+/+/set/+"
    self.mqtt_client.subscribe(cmd_topic, qos=1)
    logger.info(f"已訂閱控制指令: {cmd_topic}")
    for ha_mgr in self.ha_managers.values():
        ha_mgr.publish_gateway_online()
        ha_mgr.send_discovery(cleanup=False)

def _on_mqtt_message(self, msg):
    """
    paho 執行緒收到訊息時的橋接點

    self._loop 在 start() 裡由 get_running_loop() 取得，
    與 asyncio.run() 建立的 loop 是同一個物件
    call_soon_threadsafe 將 put_nowait 安全排入正確的 loop
    """
    if self._loop is None or self._loop.is_closed():
        return

    def _put():
        try:
            self._cmd_queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.error(f"[MQTT Bridge] 指令 Queue 滿，丟棄 topic={msg.topic}")

    self._loop.call_soon_threadsafe(_put)

async def _mqtt_consumer_task(self):
    """asyncio 端消費橋接 Queue，零延遲推入快車道"""
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
    """
    每 60 秒發布一次網關底層健康數據

    數據來源：
      bus_master.device_states：真實的 timeout_count / success_count / online
      _cmd_queue.qsize()：當前待處理指令數
      driver.reconnect_count：若 Driver 後續加入則自動生效（None 則不發出）

    topic: {node_id}/health（不走 HA Discovery，供 Telegraf/Node-RED 撈取）
    """
    logger.info("[Health Monitor] 已啟動")
    health_topic = f"{self.node_id}/health"

    while self.running:
        await asyncio.sleep(60)

        if not self.mqtt_client:
            continue

        # 從 bus_master.device_states 聚合真實數據
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

        # driver reconnect_count：未實作時不發出誤導性 0
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
# 生命週期
# =========================================================================

async def start(self):
    cfg = self._load_config()
    sys_cfg = cfg.get("system", {})
    self.node_id = sys_cfg.get("node_id", "edge_gw_01")

    log_level = sys_cfg.get("log_level", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    # 在 coroutine 內取得正確的 running loop
    # asyncio.run() 建立的新 loop 在此才是 running 狀態
    self._loop = asyncio.get_running_loop()

    # 1. Driver
    drv_cfg = cfg.get("driver", {})
    self.driver = RobustAsyncTcpDriver(
        host=self._require(drv_cfg, "host"),
        port=self._require(drv_cfg, "port"),
        timeout=drv_cfg.get("timeout", 1.0),
        inter_frame_delay=drv_cfg.get("inter_frame_delay", 0.18),
        connect_timeout=drv_cfg.get("connect_timeout", 5.0),
        idle_timeout=drv_cfg.get("idle_timeout", 0.03),
        max_response_bytes=drv_cfg.get("max_response_bytes", 2048),
        max_frame_time=drv_cfg.get("max_frame_time", 1.0),
    )
    await self.driver.connect()

    # 2. Bus Master
    self.bus_master = BusMasterScheduler(self.driver)

    # 3. MQTT
    mqtt_cfg = cfg.get("mqtt", {})
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

    # 橋接：paho on_message → _cmd_queue（self._loop 已在上方設定完畢）
    _original_on_message = self.mqtt_client._on_message
    def _bridged_on_message(client, userdata, msg):
        _original_on_message(client, userdata, msg)
        self._on_mqtt_message(msg)
    self.mqtt_client.client.on_message = _bridged_on_message

    # 4. 工廠模式載入設備
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
        )
        self.ha_managers[uid] = ha_mgr

        self.bus_master.register_device(
            uid=uid,
            adapter=adapter,
            ha_manager=ha_mgr,
            poll_interval=poll_interval,
        )
        logger.info(f"✅ 設備已掛載: UID={uid} type={device_type} adapter={adapter_name}")

    # 5. 起飛
    self.running = True
    self.mqtt_client.connect()
    self.bus_master.start()
    asyncio.create_task(self._mqtt_consumer_task())
    asyncio.create_task(self._health_monitor_task())

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

    for ha_mgr in self.ha_managers.values():
        try:
            ha_mgr.publish_gateway_offline()
        except Exception:
            pass

    if self.mqtt_client:
        self.mqtt_client.disconnect()

    if self.driver:
        await self.driver.disconnect()

    logger.info("💤 系統已安全停止")
```

# =============================================================================

# 進入點與訊號攔截

# =============================================================================

if **name** == “**main**”:
gateway = EdgeGateway(“config.yaml”)

```
def handle_signal(*args):
    """
    signal handler 必須是同步函數

    gateway._loop 在 start() 裡設定，signal 觸發時已是正確的 running loop
    call_soon_threadsafe 確保 stop() 在 event loop 執行緒內安全排程
    """
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
```
