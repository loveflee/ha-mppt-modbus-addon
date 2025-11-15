# /app/main.py
import json
import sys
import os
import mppt5

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

    try:
        # 1. 載入 HA Add-on 設定
        options = load_options()
        # 由於 run.sh 已經打印了大部分配置，這裡不再重複打印整個字典
        # print(f"✅ 成功載入配置。") 

        # 2. 執行 mppt5 模組的主邏輯
        mppt5.run(options)

    except Exception as e:
        print(f"❌ 程式發生例外: {e}")
        # 在主程式中發生錯誤時，等待一段時間再退出，避免頻繁重啟
        import time
        time.sleep(5)
        sys.exit(1)

if __name__ == "__main__":
    main()
