import logging
import os
from src.utils import fetch_app_data_path

logger = logging.getLogger("OLED Customizer")
file_handler = None

def toggle_debug_logging(enabled: bool):
    global file_handler
    root_logger = logging.getLogger()
    
    if enabled:
        if file_handler: return # Already enabled
        
        log_path = fetch_app_data_path("debug.log")
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
        
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        
        root_logger.addHandler(file_handler)
        root_logger.setLevel(logging.DEBUG)
        logger.info(f"Debug logging enabled. File: {log_path}")
    else:
        if file_handler:
            logger.info("Debug logging disabled.")
            root_logger.removeHandler(file_handler)
            file_handler.close()
            file_handler = None
            
        root_logger.setLevel(logging.INFO)

def is_debug_enabled():
    return file_handler is not None
