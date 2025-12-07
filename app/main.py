import asyncio
import logging
import signal
import sys
import yaml
from core_logging import setup_global_logging
from core_mqtt import RobustMQTTClient # MQTT 保持原樣 (它有自己的 Thread)
from core_tcp import AsyncTCPClient    # 🟢 換成 AsyncTCPClient
from ampinvt_proto import AsyncAmpinvtProtocol # 🟢 換成 AsyncProtocol
from command_handler import AsyncCommandHandler # 🟢 換成 AsyncHandler
from ha_manager import HAManager
import mppt_register_map as rmap

logger = None
shutdown_event = asyncio.Event()

def load_config():
    try:
        with open("config.yaml", "r") as f: config = yaml.safe_load(f)
        modbus = config.get('modbus', {})
        raw = modbus.get('unit_ids', "1")
        if isinstance(raw, str):
            modbus['unit_ids'] = [int(x) for x in raw.split(',') if x.strip().isdigit()]
        elif isinstance(raw, int):
            modbus['unit_ids'] = [raw]
        return config
    except: return None

# 🟢 [關鍵] MQTT 橋接器：把 Paho 的訊息丟進 Async Queue
def mqtt_bridge_callback(client, userdata, msg, loop, async_queue):
    if msg:
        try:
            loop.call_soon_threadsafe(async_queue.put_nowait, msg)
        except: pass

async def task_mqtt_processor(queue, handler, lock):
    """
    任務 A: MQTT 指令處理器 (高優先級)
    """
    logger.info("🟢 [Task] 指令監聽器啟動")
    while not shutdown_event.is_set():
        try:
            # 等待指令 (非阻塞)
            msg = await queue.get()
            
            payload = msg.payload.decode().strip()
            topic = msg.topic
            logger.info(f"⚡ 插隊指令: {topic} -> {payload}")

            # 🟢 [關鍵] 申請鎖 (如果輪詢正在進行，這裡會等待直到輪詢結束)
            async with lock:
                await handler.process_message(topic, payload)
            
            queue.task_done()
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"指令任務異常: {e}")

async def task_polling_loop(cfg, protocol, ha_mgr, lock):
    """
    任務 B: 週期性輪詢 (低優先級)
    """
    logger.info("🟢 [Task] 數據輪詢器啟動")
    unit_ids = cfg['modbus']['unit_ids']
    poll_int = cfg['polling']['poll_interval']
    delay = cfg['polling']['delay_between_units']
    
    offline_devices = {} # 黑名單機制 (時間戳)

    while not shutdown_event.is_set():
        start_time = asyncio.get_running_loop().time()
        
        for uid in unit_ids:
            if shutdown_event.is_set(): break

            # 黑名單檢查
            if uid in offline_devices:
                if asyncio.get_running_loop().time() < offline_devices[uid]: continue
                else: logger.info(f"🔄 重試設備 #{uid}")

            # 🟢 [關鍵] 申請鎖 (確保總線獨佔)
            async with lock:
                try:
                    data = await protocol.read_b1_data(uid)
                    if data:
                        # 解碼與發佈 (這部分很快，不需要佔用鎖)
                        vals = protocol.decode(data, rmap.B1_INFO)
                        bits = protocol.decode(data, rmap.B3_STATUS_BITS, is_bits=True)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        
                        if uid in offline_devices: del offline_devices[uid]
                    
                except Exception as e:
                    logger.warning(f"⚠️ 設備 #{uid} 讀取失敗")
                    offline_devices[uid] = asyncio.get_running_loop().time() + 60

            # 釋放鎖後，休息一下 (這段時間 MQTT 可以插隊)
            await asyncio.sleep(delay)

        # 確保週期時間
        elapsed = asyncio.get_running_loop().time() - start_time
        sleep_time = max(0.1, poll_int - elapsed)
        await asyncio.sleep(sleep_time)

async def async_main():
    global logger
    config = load_config()
    if not config: return

    debug_mode = config.get('system', {}).get('debug', False)
    setup_global_logging(debug_mode)
    logger = logging.getLogger("Main")
    logger.info("🚀 啟動 V6.0 Asyncio 工業級架構")

    # 建立 Async 物件
    tcp = AsyncTCPClient(
        config['modbus']['host'], 
        config['modbus']['port'], 
        config['modbus']['timeout']
    )
    protocol = AsyncAmpinvtProtocol(tcp, debug=debug_mode)
    cmd_handler = AsyncCommandHandler(protocol, config.get('system', {}).get('timezone_offset', 8))
    
    # MQTT 橋接
    mqtt_cfg = config['mqtt']
    mqtt = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    ha_mgr = HAManager(mqtt, mqtt_cfg)
    
    # 建立 Queue 與 Loop 引用
    loop = asyncio.get_running_loop()
    mqtt_queue = asyncio.Queue()
    
    # 設定 Callback 橋接
    mqtt.client.on_message = lambda c, u, m: mqtt_bridge_callback(c, u, m, loop, mqtt_queue)
    
    # 連線與訂閱
    logger.info(f"👻 設定 LWT: {ha_mgr.availability_topic}")
    mqtt.set_lwt(ha_mgr.availability_topic, payload="offline", retain=True)
    mqtt.connect()
    
    ha_mgr.send_discovery(config['modbus']['unit_ids'])
    mqtt.publish(ha_mgr.availability_topic, "online", retain=True)
    for t in ["switch", "button", "number", "select"]:
        mqtt.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")

    # 🟢 [核心] 建立 Modbus 互斥鎖
    modbus_lock = asyncio.Lock()

    # 啟動任務
    t1 = asyncio.create_task(task_mqtt_processor(mqtt_queue, cmd_handler, modbus_lock))
    t2 = asyncio.create_task(task_polling_loop(config, protocol, ha_mgr, modbus_lock))

    # Signal 處理
    def signal_handler():
        logger.info("🛑 收到停止訊號")
        shutdown_event.set()
        t1.cancel()
        t2.cancel()

    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    try:
        await asyncio.gather(t1, t2)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("👋 系統關閉，清理連線...")
        await tcp.close()
        mqtt.publish(ha_mgr.availability_topic, "offline", retain=True)
        # mqtt.disconnect()

if __name__ == "__main__":
    try:
        # Windows 上可能需要 ProactorEventLoop，但 Docker (Linux) 不需要
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
