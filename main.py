import logging
from psutil import pid_exists
from os import getpid, path, makedirs, remove
import atexit
import sys
import psutil
import time
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from version import __version__
from src.Config import Config
from src.DisplayManager import DisplayManager
from src.utils import fetch_app_data_path


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

FPS = 10


if __name__ == "__main__":
    logger = logging.getLogger("OLED Customizer")

    # Create app data directory if it doesn't exist
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
