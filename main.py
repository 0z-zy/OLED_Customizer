import logging
from psutil import pid_exists
import os
from os import getpid, path, makedirs, remove
import atexit
import sys
import psutil
import time
import asyncio
import sys
import traceback

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- FIX: Enforce CWD to script directory to fix startup issues ---
if getattr(sys, 'frozen', False):
    # If pyinstaller exe, use strict dir
    os.chdir(os.path.dirname(sys.executable))
else:
    # If normal python, use script dir
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

from version import __version__
from src.Config import Config
from src.DisplayManager import DisplayManager
from src.utils import fetch_app_data_path



def setup_logging():
    try:
        app_data_path = fetch_app_data_path()
        if not path.exists(app_data_path):
            makedirs(app_data_path)
        
        log_file = path.join(app_data_path, "debug.log")
        
        handlers = [logging.FileHandler(log_file, mode='w', encoding='utf-8')]
        if sys.stdout:
            handlers.append(logging.StreamHandler(sys.stdout))
            
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=handlers
        )
    except Exception as e:
        # If logging fails effectively, we are in trouble. Try to write to a local fallback file?
        pass

def unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Redundant backup log just in case logging module failed
    try:
        err_path = fetch_app_data_path("crash.log")
        with open(err_path, "a") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] UNCAUGHT EXCEPTION:\n")
            # Use traceback module to format
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except: 
        pass

sys.excepthook = unhandled_exception

FPS = 10


if __name__ == "__main__":
    try:
        setup_logging()
        logger = logging.getLogger("OLED Customizer")
        
        # Create app data directory if it doesn't exist (redundant but safe)
        app_data_path = fetch_app_data_path()
        if not path.exists(app_data_path):
            logger.info("Creating app data directory at %s", app_data_path)
            makedirs(app_data_path)

        lock_file_path = path.join(app_data_path, ".lock")

        # Check if another instance is already running through lock file which contains PID
        if path.exists(lock_file_path):
            with open(lock_file_path, "r") as f:
                content = f.read().strip()
                if content.isdigit():
                    pid = int(content)
                    if pid_exists(pid):
                        logger.warning("Another instance found (PID %d). Terminating it...", pid)
                        try:
                            p = psutil.Process(pid)
                            p.terminate()
                            p.wait(timeout=5)
                        except Exception as e:
                            logger.error(f"Failed to terminate old instance: {e}")
                            # Force kill if terminate fails
                            try:
                                os.kill(pid, 9)
                            except:
                                pass
                        
                        # Wait a bit for file lock to release
                        time.sleep(1)

        # Write lock file with PID to prevent multiple instances
        with open(lock_file_path, "w") as lock_file:
            lock_file.write(str(getpid()))

        # Remove lock file on exit
        def _remove_lock():
            try:
                if path.exists(lock_file_path):
                    remove(lock_file_path)
            except Exception as e:
                logger.error("Failed to remove lock file: %s", e)

        atexit.register(_remove_lock)

        config = Config(
            {
                "pause_steps": FPS * 2,
            }
        )

        display_manager = DisplayManager(config, FPS)

        display_manager.init()
        logger.info("OLED Customizer running in version %s", __version__)
        display_manager.run()
        
    except Exception as e:
        # Only catch main loop initialization errors here
        # sys.excepthook handles the rest, but we keep this for specific logging
        logging.critical("Critical error in main: %s", e, exc_info=True)
        raise
