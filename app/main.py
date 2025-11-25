# /app/main.py
import json
import sys
import os
import time
import ampinvt_mppt


def load_options():
    """ 載入 /data/options.json 裡的設定 """
    options_file = "/data/options.json"
    if not os.path.exists(options_file):
        print("❌ 錯誤: 找不到 HA Add-on 設定檔 /data/options.json。")
        sys.exit(1)

    with open(options_file, 'r') as f:
        options = json.load(f)
    return options


def main():
    print(">>> 啟動 MPPT Modbus MQTT Poller <<<")

    # ✅ 剛啟動時先等待 10 秒，讓 MQTT / Modbus gateway / HA 都穩定
    startup_delay = 20
    print(f"⏳ 啟動延遲 {startup_delay} 秒，等待系統服務就緒...")
    time.sleep(startup_delay)

    try:
        # 1. 載入 HA Add-on 設定
        options = load_options()

        # 2. 執行 ampinvt_mppt 模組的主邏輯
        ampinvt_mppt.run(options)

    except Exception as e:
        print(f"❌ 程式發生例外: {e}")
        # 在主程式中發生錯誤時，等待一段時間再退出，避免頻繁重啟
        time.sleep(5)
        sys.exit(1)


if __name__ == "__main__":
    main()
