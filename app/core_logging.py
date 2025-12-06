import logging
import sys

def setup_global_logging(debug_mode: bool):
    """
    配置全域日誌系統
    :param debug_mode: 是否開啟除錯模式 (顯示 DEBUG 等級)
    """
    # 1. 定義格式
    # %(asctime)s: 時間
    # %(name)s:    模組名稱 (例如 Main, CMD, TCP)
    # %(levelname)s: 等級 (INFO, ERROR...)
    # %(message)s: 訊息內容
    log_format = "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"
    date_format = "%H:%M:%S" # 簡潔時間格式

    # 2. 決定等級
    level = logging.DEBUG if debug_mode else logging.INFO

    # 3. 設定 Root Logger
    # 使用 stdout 確保 Docker logs 能抓到
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除舊的 handler 避免重複打印 (Reload 時有用)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(handler)
    
    # 4. 抑制一些太囉唆的第三方庫日誌 (例如 Paho MQTT 底層)
    logging.getLogger("paho").setLevel(logging.WARNING)

    return logging.getLogger("System")
