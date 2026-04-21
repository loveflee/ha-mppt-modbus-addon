import logging
import sys

def setup_global_logging(debug_mode: bool):
    log_format = "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"
    date_format = "%H:%M:%S"
    level = logging.DEBUG if debug_mode else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(handler)
    logging.getLogger("paho").setLevel(logging.WARNING)
