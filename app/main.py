import time
import yaml
import signal
import sys
from datetime import datetime, timedelta, timezone # 🟢 [新增] 引入時間處理工具，為了讓 MPPT 知道現在幾點

# 匯入我們自己寫的模組 (就像組裝積木一樣)
import mppt_register_map as rmap        # 這是藏寶圖：告訴程式碼去哪裡讀電壓、電流
from core_tcp import RobustTCPClient    # 這是電話機：負責打電話給 Modbus 設備
from core_mqtt import RobustMQTTClient # 這是傳令兵：負責跟 Home Assistant 講話
from ampinvt_proto import AmpinvtProtocol # 這是翻譯官：把 Hex 轉成人類看得懂的數字
from ha_manager import HAManager        # 這是外交官：負責跟 HA 註冊裝置

# --- 全域變數 (Global Variables) ---
# 放在這裡是為了讓不同的函式 (例如關閉程式時) 都能存取到它們
mqtt_client = None
ha_mgr = None
app_config = None

def load_config():
    """
    📖 讀取設定檔的貼心小幫手
    功能：讀取 config.yaml，並且自動修正使用者可能填錯的格式
    """
    try:
        with open("config.yaml", "r") as f: 
            config = yaml.safe_load(f)
            
        # --- 🔧 自動防呆機制 ---
        # 使用者在 YAML 裡填寫 unit_ids: "1, 2, 3" (字串)
        # 但程式跑迴圈需要的是 [1, 2, 3] (列表)
        # 這裡負責做轉換，不管使用者怎麼填都能跑
        modbus_section = config.get('modbus', {})
        raw_ids = modbus_section.get('unit_ids', "1")
        
        if isinstance(raw_ids, str):
            # 如果是字串，就切開並把空白修掉，轉成數字
            id_list = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
            config['modbus']['unit_ids'] = id_list
        elif isinstance(raw_ids, int):
            # 如果只有填一個數字 1，就幫他包成列表 [1]
            config['modbus']['unit_ids'] = [raw_ids]
        elif isinstance(raw_ids, list):
            # 如果已經是列表，確保裡面都是數字
            config['modbus']['unit_ids'] = [int(x) for x in raw_ids]
            
        return config
    except Exception as e:
        print(f"❌ 哎呀！設定檔讀取失敗: {e}")
        return None

def graceful_exit(signum, frame):
    """
    👋 優雅退場機制
    當 Docker 或使用者按下 Ctrl+C 時，這個函式會被觸發。
    就像離開房間要關燈一樣，我們要確保連線都被乾淨地切斷。
    """
    print(f"\n🛑 收到關閉指令 ({signum})，正在收拾行李...")
    
    # 如果有設定「結束時清除 HA 實體」，就在這裡執行
    if app_config and ha_mgr and mqtt_client:
        reset_on_exit = app_config.get('mqtt', {}).get('reset_discovery_on_exit', False)
        
        if reset_on_exit:
            print("🧹 正在清除 Home Assistant 上的裝置註冊...")
            try:
                unit_ids = app_config['modbus']['unit_ids']
                ha_mgr.clear_all_discovery(unit_ids)
                time.sleep(2) # 給 HA 一點時間反應
            except Exception as e:
                print(f"❌ 清除失敗: {e}")
    
    if mqtt_client:
        print("🔌 斷開 MQTT 連線...")
        
    print("👋 程式結束，Bye Bye!")
    sys.exit(0) # 0 代表「正常結束」，Docker 不會報錯

# 🟢 [新增] 取得當地時間的小幫手
def get_local_time(offset_hours):
    """
    🌍 計算正確的當地時間
    Docker 裡面通常是 UTC+0 (格林威治時間)，
    我們需要加上使用者設定的時區 (例如台灣是 +8)，
    這樣寫入機器的時候才不會慢 8 小時。
    """
    utc_now = datetime.now(timezone.utc)
    local_dt = utc_now + timedelta(hours=offset_hours)
    return local_dt

def main():
    # 宣告我們要使用外面的全域變數
    global mqtt_client, ha_mgr, app_config
    
    # 1. 載入設定 (第一關)
    app_config = load_config()
    if not app_config:
        print("❌ 設定檔壞了，程式無法啟動。")
        sys.exit(1) # 1 代表「異常結束」，Docker 會記錄錯誤

    modbus_cfg = app_config['modbus']
    mqtt_cfg = app_config['mqtt']
    sys_cfg = app_config.get('system', {}) # 🟢 取得系統設定
    
    # 🟢 [新增] 讀取時區設定 (預設是 8，也就是台灣時間)
    tz_offset = sys_cfg.get('timezone_offset', 8)
    
    # 2. 註冊監聽器：告訴系統，如果有人按 Ctrl+C，請執行 graceful_exit
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)
    
    print(f"🚀 MPPT 監控系統啟動中 (V4.7 - 貼心註解 + 時區版)")
    print(f"🌍 目前設定時區補償: UTC+{tz_offset}")

    # 3. 初始化各大核心模組 (建立物件)
    # 這裡只是把工具準備好，還沒開始工作
    tcp = RobustTCPClient(modbus_cfg['host'], modbus_cfg['port'], modbus_cfg['timeout'])
    mqtt_client = RobustMQTTClient(mqtt_cfg['broker'], mqtt_cfg['port'], mqtt_cfg['username'], mqtt_cfg['password'])
    
    protocol = AmpinvtProtocol(tcp, debug=sys_cfg.get('debug', False))
    ha_mgr = HAManager(mqtt_client, mqtt_cfg)

    # 4. 設定 MQTT 連線後的動作
    # 這是「非同步」的觀念：我們定義好「連上後要做什麼」，但現在還不做
    def on_mqtt_ready():
        # A. 遞名片：跟 HA 說我們有哪些感測器
        ha_mgr.send_discovery(modbus_cfg['unit_ids'])
        
        # B. 豎起耳朵：訂閱所有控制指令
        # + 代表萬用字元，不管哪個開關被按，我都聽得到
        topics = ["switch", "button", "number", "select"]
        for t in topics:
            mqtt_client.subscribe(f"{mqtt_cfg['discovery_prefix']}/{t}/+/+/set")
        print(f"👂 已就位，隨時準備接收 HA 指令")

    mqtt_client.on_connected_callback = on_mqtt_ready
    mqtt_client.connect() # 這裡才真正開始連線

    # --- 🐶 看門狗變數 ---
    consecutive_errors = 0    
    MAX_ERRORS = 20           # 容忍 20 次連續失敗 (大約 1 分鐘)

    # 5. 主迴圈 (程式的心臟)
    # 這裡會一直跑，直到世界末日或當機
    while True:
        
        # ==========================
        # 任務 A: 處理 MQTT 指令 (接收者)
        # ==========================
        try:
            # 檢查信箱有沒有信 (Queue)
            while not mqtt_client.msg_queue.empty():
                msg = mqtt_client.msg_queue.get()
                
                # 簡單的資料清理 (防呆)
                if isinstance(msg, dict):
                    topic = msg.get('topic'); payload_raw = msg.get('payload')
                else:
                    topic = getattr(msg, 'topic', None); payload_raw = getattr(msg, 'payload', None)

                if not topic or payload_raw is None: continue

                # 把收到的 Bytes 轉成字串
                if isinstance(payload_raw, bytes): payload = payload_raw.decode('utf-8').strip()
                else: payload = str(payload_raw).strip()

                print(f"📩 收到指令 [{topic}]: {payload}")
                
                try:
                    # 解析 Topic：homeassistant/number/mppt_1/equalize_vol/set
                    # 利用 split('/') 切割字串來找出是誰發的
                    parts = topic.split('/') 
                    key = parts[-2]          # 例如: equalize_vol
                    entity_base = parts[-3]  # 例如: mppt_1
                    domain = parts[-4]       # 例如: number
                    uid = int(entity_base.split('_')[-1]) # 取出 ID: 1

                    # 👉 處理開關 (Switch)
                    if domain == "switch":
                        switch_def = rmap.CONTROL_SWITCHES.get(key)
                        if switch_def:
                            # 判斷是開還是關，發送對應的 C0 命令
                            cmd = switch_def['on_code'] if payload.upper()=="ON" else switch_def['off_code']
                            protocol.write_c0_command(uid, cmd)

                    # 👉 處理按鈕 (Button)
                    elif domain == "button":
                        btn_def = rmap.CONTROL_BUTTONS.get(key)
                        if btn_def: 
                            # 🟢 [新增] 判斷是不是「時間同步」按鈕 (代碼 0xDF)
                            if btn_def.get('code') == 0xDF:
                                # 算出正確的當地時間
                                local_dt = get_local_time(tz_offset)
                                print(f"⏰ 執行時間同步: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                # 呼叫 protocol 把時間寫入機器
                                protocol.write_time_sync(uid, local_dt)
                            else:
                                # 是一般按鈕 (例如消音)，直接發送代碼
                                protocol.write_c0_command(uid, btn_def['code'])

                    # 👉 處理數值滑桿 (Number) - 這裡用到 D0 指令
                    elif domain == "number":
                        # 1. 先去 Map 裡找這個 key 對應的 Hex Code
                        target_item = None
                        target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key:
                                target_item = item; target_code = code; break
                        
                        # 2. 找到了就寫入
                        if target_item:
                            val = float(payload)
                            print(f"👉 設定參數 [{key}] = {val}")
                            # 這裡會自動處理倍率 (例如 58V -> 5800)
                            protocol.write_d0_command(uid, target_code, val, target_item['scale'], target_item['valid_bytes'])

                    # 👉 處理下拉選單 (Select)
                    elif domain == "select":
                        target_item = None
                        target_code = None
                        for code, item in rmap.D0_PARAMS.items():
                            if item['key'] == key:
                                target_item = item; target_code = code; break
                        
                        if target_item:
                            # 這裡比較複雜：要把中文選項轉回數字 (例如 "鋰電池" -> 3)
                            # 我們去 B1_INFO 找對應的 Map
                            map_dict = None
                            for b1_item in rmap.B1_INFO:
                                if b1_item.get('key') == target_item.get('ha', {}).get('link_b1'):
                                    map_dict = b1_item.get('map')
                                    break
                            
                            if map_dict:
                                int_val = None
                                # 策略 1: 用名字找數字
                                for k, v in map_dict.items():
                                    if v == payload: int_val = k; break
                                # 策略 2: 如果字串是 "3:鋰電池"，直接抓前面的 3
                                if int_val is None and ":" in payload:
                                    try:
                                        potential_id = int(payload.split(':')[0])
                                        if potential_id in map_dict: int_val = potential_id
                                    except: pass

                                if int_val is not None:
                                    print(f"👉 設定模式 [{key}] = {payload} (數值={int_val})")
                                    protocol.write_d0_command(uid, target_code, int_val, 1, target_item['valid_bytes'])
                                else:
                                    print(f"⚠️ 找不到選項對應的數值: {payload}")

                except Exception as e:
                    print(f"⚠️ 指令解析失敗: {e}")

        except Exception as e:
            print(f"⚠️ MQTT 迴圈發生錯誤 (不影響主程式): {e}")

        # ==========================
        # 任務 B: 輪詢數據 (Polling) - 這是有看門狗保護的！
        # ==========================
        try:
            any_success = False # 標記：這一輪有沒有任何一台機器回應？

            for uid in modbus_cfg['unit_ids']:
                try:
                    # 1. 讀取數據 (Read)
                    raw_data = protocol.read_b1_data(uid)
                    
                    if raw_data:
                        # 2. 解碼 (Decode)
                        vals = protocol.decode(raw_data, rmap.B1_INFO)
                        bits = protocol.decode(raw_data, rmap.B3_STATUS_BITS, is_bits=True)
                        
                        # 3. 發布 (Publish)
                        ha_mgr.publish_state(uid, vals, "state_b1")
                        ha_mgr.publish_state(uid, bits, "state_bits")
                        
                        any_success = True # 只要有一台成功，就算系統活著！
                        
                    # 稍微休息一下，避免連續讀取太快塞車
                    time.sleep(app_config['polling']['delay_between_units'])
                    
                except Exception as e_inner:
                    # 單台失敗我們不中斷，只做紀錄，繼續讀下一台
                    # pass 代表「這沒什麼，繼續做」
                    pass 
            
            # --- 🐶 看門狗檢查點 ---
            if any_success:
                consecutive_errors = 0 # 呼！還活著，計數器歸零
            else:
                consecutive_errors += 1 # 糟糕，全軍覆沒，記過一次
                # 每 5 次提醒一次，避免 Log 被洗版
                if consecutive_errors % 5 == 0:
                    print(f"⚠️ [Watchdog] 警告：連續讀取失敗 ({consecutive_errors}/{MAX_ERRORS})")

            # 🔥 最終審判：如果連續失敗次數超過上限
            if consecutive_errors >= MAX_ERRORS:
                print("❌ [Watchdog] 系統判定為嚴重故障 (可能是硬體卡死)")
                print("💀 執行強制重啟指令...")
                sys.exit(1) # 回傳 1 告訴 Docker：「我掛了，請幫我重啟」

        except Exception as e:
            print(f"⚠️ Main Loop 發生未預期錯誤: {e}")
            consecutive_errors += 1
            if consecutive_errors >= MAX_ERRORS:
                sys.exit(1)
            
        # 每一輪巡邏結束，休息一下 (例如 3 秒)
        time.sleep(app_config['polling']['poll_interval'])

if __name__ == "__main__":
    main()
