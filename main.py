import logging
import logging.handlers
from psutil import pid_exists
import os
from os import getpid, path, makedirs, remove
import atexit
import sys
import psutil
import time
import asyncio
import traceback
import faulthandler

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

def cleanup_old_updates():
    """Removes the leftover .old executable from an in-place update if it exists."""
    if getattr(sys, 'frozen', False):
        try:
            exe_path = sys.executable
            old_path = exe_path + ".old"
            if os.path.exists(old_path):
                os.remove(old_path)
                # logging isn't set up yet, so we just silently remove it
        except Exception:
            pass

# Run cleanup immediately
cleanup_old_updates()



def setup_logging(debug=False):
    try:
        app_data_path = fetch_app_data_path()
        if not path.exists(app_data_path):
            makedirs(app_data_path)
        
        log_file = path.join(app_data_path, "debug.log")
        
        level = logging.DEBUG if debug else logging.INFO
        
        # Use RotatingFileHandler to prevent massive log files (max 2MB, keep 2 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, mode='a', maxBytes=2*1024*1024, backupCount=2, encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        
        handlers = [file_handler]
        if sys.stdout:
            handlers.append(logging.StreamHandler(sys.stdout))
            
        logging.basicConfig(
            level=level,
            format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=handlers
        )
        
        # IMPORTANT: Silence noisy loggers that flood the debug log
        # urllib3 logs every HTTP request at DEBUG level (~3/sec = 20MB in 8 hours)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        
        # comtypes logs every AddRef/Release pointer which floods logs when rendering
        logging.getLogger("comtypes").setLevel(logging.WARNING)
        logging.getLogger("pycaw").setLevel(logging.WARNING)
        
        # Also silence charset_normalizer and other noisy libs
        logging.getLogger("charset_normalizer").setLevel(logging.WARNING)
        logging.getLogger("PIL").setLevel(logging.WARNING)
        
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
        # Enable faulthandler to catch crashes from COM/WinRT/pythonnet
        # These can cause hard crashes that bypass Python's exception handler
        fault_log_path = None
        try:
            from src.utils import fetch_app_data_path as _fap
            app_data_dir = _fap()
            # Ensure directory exists BEFORE trying to open fault.log
            if not path.exists(app_data_dir):
                makedirs(app_data_dir)
            fault_log_path = path.join(app_data_dir, "fault.log")
            fault_file = open(fault_log_path, 'a')
            faulthandler.enable(file=fault_file)
        except Exception:
            # Fallback to stderr only if it exists (not None in frozen apps)
            if sys.stderr is not None:
                faulthandler.enable()
            # Otherwise just skip faulthandler - better than crashing
        
        # Load preferences early to check for debug_enabled
        from src.UserPreferences import UserPreferences
        prefs = UserPreferences()
        prefs.load_preferences()
        debug_on = prefs.get_preference("debug_enabled")
        
        setup_logging(debug=debug_on)
        logger = logging.getLogger("OLED Customizer")
        
        # V5: Initialize COM on main thread for stability
        try:
            import ctypes
            ctypes.windll.ole32.CoInitialize(0)
            logger.debug("COM initialized on main thread.")
        except Exception as e:
            logger.warning(f"Main thread COM init failed: {e}")
        
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
        
        # If debug was enabled in prefs, make sure debug_utils knows it's "enabled" 
        # (even if it doesn't add a second handler)
        if debug_on:
            from src.debug_utils import toggle_debug_logging
            toggle_debug_logging(True)

        display_manager.init()
        logger.info("OLED Customizer running in version %s", __version__)
        display_manager.run()
        
    except Exception as e:
        # Only catch main loop initialization errors here
        # sys.excepthook handles the rest, but we keep this for specific logging
        logging.critical("Critical error in main: %s", e, exc_info=True)
        raise
