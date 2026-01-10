from os import path, getenv
import winreg
import sys
import psutil

import logging

logger = logging.getLogger("OLED Customizer.Utils")

def fetch_app_data_path(content=''):
    return path.abspath(getenv('APPDATA') + '/OLED Customizer/' + content)

def fetch_content_path(content):
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = path.join(path.dirname(path.abspath(__file__)), '../')
    
    return path.abspath(path.join(base_path, content))

def normalize_text(text: str) -> str:
    """
    Replaces Turkish characters with their ASCII equivalents to prevent rendering issues on the OLED.
    """
    if not text:
        return ""
        
    replacements = {
        "ş": "s", "Ş": "S",
        "ç": "c", "Ç": "C",
        "ü": "u", "Ü": "U",
        "ö": "o", "Ö": "O",
        "ğ": "g", "Ğ": "G",
        "ı": "i", "İ": "I",
    }
    
    for turkey_char, ascii_char in replacements.items():
        text = text.replace(turkey_char, ascii_char)
        
    return text

def set_startup(enable: bool):
    """
    Add or remove the application from Windows Startup via Task Scheduler.
    Uses Task Scheduler instead of Registry to allow running with highest privileges
    without UAC prompts at login.
    """
    import subprocess
    
    task_name = "OLED Customizer"
    
    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            # Dev mode - not ideal but acceptable
            exe_path = sys.executable
        
        if enable:
            # First, delete any existing task to avoid conflicts
            subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Create a new scheduled task that runs at logon with highest privileges
            # /sc onlogon = trigger at user logon
            # /rl highest = run with highest privileges (admin, no UAC prompt)
            # /it = interactive (allows GUI)
            result = subprocess.run(
                [
                    'schtasks', '/create',
                    '/tn', task_name,
                    '/tr', f'"{exe_path}"',
                    '/sc', 'onlogon',
                    '/rl', 'highest',
                    '/it',
                    '/f'  # Force overwrite if exists
                ],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                logger.info(f"Added to startup via Task Scheduler: {exe_path}")
                # Also clean up any old registry entry
                _cleanup_old_registry_startup()
            else:
                logger.error(f"Failed to create scheduled task: {result.stderr}")
        else:
            # Delete the scheduled task
            result = subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                logger.info("Removed from startup (Task Scheduler)")
            else:
                # Task might not exist, that's okay
                logger.info("Startup task not found or already removed")
            
            # Also clean up any old registry entry
            _cleanup_old_registry_startup()
                
    except Exception as e:
        logger.error(f"Failed to change startup settings: {e}")

def _cleanup_old_registry_startup():
    """Remove any old registry-based startup entry."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "OLED Customizer"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, app_name)
            logger.info("Cleaned up old registry startup entry")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

def is_startup_enabled() -> bool:
    """Check if the startup task exists in Task Scheduler."""
    import subprocess
    
    task_name = "OLED Customizer"
    try:
        result = subprocess.run(
            ['schtasks', '/query', '/tn', task_name],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to check startup status: {e}")
        return False

def is_process_running(process_names):
    """
    Check if any of the given process names are running.
    """
    if isinstance(process_names, str):
        process_names = [process_names]
        
    process_names = [p.lower() for p in process_names]
    
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'].lower() in process_names:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def find_steelseries_gg_path():
    """
    Attempts to locate the SteelSeries GG executable in common installation directories.
    """
    common_paths = [
        r"C:\Program Files\SteelSeries\GG\SteelSeriesGG.exe",
        r"C:\Program Files (x86)\SteelSeries\GG\SteelSeriesGG.exe",
        r"C:\Program Files\SteelSeries\SteelSeries Engine 3\SteelSeriesEngine3.exe",
        r"C:\Program Files (x86)\SteelSeries\SteelSeries Engine 3\SteelSeriesEngine3.exe"
    ]
    
    for p in common_paths:
        if path.exists(p):
            return p
            
    return None

def launch_process(process_path, arguments=None):
    """
    Launches a process from the given path non-blocking.
    Uses ShellExecute to handle UAC elevation if required (WinError 740).
    """
    if not process_path or not path.exists(process_path):
        return False
        
    try:
        import ctypes
        # ShellExecuteW(hwnd, operation, file, parameters, directory, show_cmd)
        
        directory = path.dirname(process_path)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", process_path, arguments, directory, 1)
        
        # Returns > 32 on success
        if ret > 32:
            logger.info(f"Launched process: {process_path} args={arguments}")
            return True
        else:
            logger.error(f"ShellExecute failed with code {ret} for {process_path}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to launch process {process_path}: {e}")
        return False
