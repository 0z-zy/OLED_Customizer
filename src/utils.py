import os
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
    Uses PowerShell to create a robust task that runs with highest privileges
    and ignores AC power restrictions.
    """
    import subprocess
    
    task_name = "OLED Customizer"
    
    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            # Dev mode - include the script path
            exe_path = f"{sys.executable}\" \"{os.path.abspath(sys.argv[0])}"
        
        if enable:
            # PowerShell script to create a robust task
            ps_cmd = f"""
            $action = New-ScheduledTaskAction -Execute '{exe_path}'
            $trigger = New-ScheduledTaskTrigger -AtLogon
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
            Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
            """
            
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                logger.info(f"Added to startup (Task Scheduler): {exe_path}")
                _cleanup_old_registry_startup()
            else:
                logger.error(f"Failed to create scheduled task: {result.stderr}")
                # Fallback to simple schtasks if PowerShell fails
                subprocess.run(
                    ['schtasks', '/create', '/tn', task_name, '/tr', f'"{exe_path}"', '/sc', 'onlogon', '/rl', 'highest', '/f'],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        else:
            # Delete the scheduled task
            subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            logger.info("Removed from startup (Task Scheduler)")
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
        r"C:\Program Files\SteelSeries\GG\SteelSeriesGGClient.exe",
        r"C:\Program Files (x86)\SteelSeries\GG\SteelSeriesGG.exe",
        r"C:\Program Files (x86)\SteelSeries\GG\SteelSeriesGGClient.exe",
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
        if not arguments:
            os.startfile(process_path)
            logger.info(f"Launched process (standard): {process_path}")
            return True
            
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
