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
    Add or remove the application from Windows Startup via Registry.
    """
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "OLED Customizer"
    
    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable  # In dev, this might be python.exe, which is not ideal but acceptable for now or use sys.argv[0]
            # Better to point to the python script if not frozen? 
            # For this user context, they rely on Launcher.exe mostly. 
            # If running from source, this might register python.exe which is tricky with args.
            # Using sys.argv[0] absolute path
            exe_path = f'"{sys.executable}" "{path.abspath(sys.argv[0])}"'

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            logger.info(f"Added to startup: {exe_path}")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                logger.info("Removed from startup")
            except FileNotFoundError:
                pass
                
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to change startup settings: {e}")

def is_startup_enabled() -> bool:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "OLED Customizer"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
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
