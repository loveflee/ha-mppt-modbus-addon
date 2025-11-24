# /app/main.py
import json
import sys
import os
import time
import logging
import ampinvt_mppt

def setup_logging(log_level_str: str) -> None:
    """
    設定全域 logging 格式與等級
    """
    level = logging.getLevelName(log_level_str.upper()) if log_level_str else logging.INFO
    if not isinstance(level, int):
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger(__name__).info(f"Logging initialized with level: {logging.getLevelName(level)}")


def load_options():
    """ 載入 /data/options.json 裡的設定 """
    logger = logging.getLogger(__name__)
    options_file = "/data/options.json"
    if not os.path.exists(options_file):
        logger.error("找不到 HA Add-on 設定檔 /data/options.json。")
        sys.exit(1)

    with open(options_file, 'r') as f:
        options = json.load(f)
    return options


def main():
    # 先用環境變數中的 LOG_LEVEL 暫時初始化 logging
    env_log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(env_log_level)
    logger = logging.getLogger(__name__)

    logger.info(">>> 啟動 MPPT Modbus MQTT Poller <<<")

    try:
        # 1. 載入 HA Add-on 設定
        options = load_options()

        # 若 options 裡有 log_level，以 options 為主，再重新設定 logging
        opt_log_level = options.get("log_level", env_log_level)
        setup_logging(opt_log_level)
        logger = logging.getLogger(__name__)
        logger.info("成功載入 Add-on 設定。")

        # 🕒 2. 啟動時先等 10 秒，讓 MQTT / Modbus gateway / HA 都有時間就緒
        wait_seconds = 10
        logger.info(f"啟動延遲 {wait_seconds} 秒，等待外部服務就緒...")
        time.sleep(wait_seconds)

        # 3. 執行 ampinvt_mppt 模組的主邏輯
        ampinvt_mppt.run(options)

    except Exception as e:
        logger.exception(f"程式發生例外: {e}")
        # 在主程式中發生錯誤時，等待一段時間再退出，避免頻繁重啟
        time.sleep(5)
        sys.exit(1)


if __name__ == "__main__":
    main()
