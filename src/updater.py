import requests
import os
import sys
import subprocess
import logging
from version import __version__

logger = logging.getLogger("OLED Customizer.Updater")

REPO_RAW_URL = "https://raw.githubusercontent.com/0z-zy/OLED_Customizer/main/version.py"
RELEASE_EXE_URL = "https://github.com/0z-zy/OLED_Customizer/releases/latest/download/OLED-Customizer.exe"

def get_latest_version():
    """Fetches the latest version string from the GitHub repo."""
    try:
        response = requests.get(REPO_RAW_URL, timeout=5)
        if response.status_code == 200:
            # Parse __version__ = "x.y.z"
            content = response.text
            for line in content.splitlines():
                if '__version__' in line:
                    version = line.split('"')[1]
                    return version
    except Exception as e:
        logger.error(f"Failed to fetch latest version: {e}")
    return None

def is_update_available():
    """Returns (True, latest_version) if an update is available, else (False, latest_version)."""
    latest = get_latest_version()
    if not latest:
        return False, None
    
    # Simple version comparison (e.g. "1.2.16" vs "1.2.17")
    # For more robust comparison, we could use packaging.version
    local_parts = [int(p) for p in __version__.split('.')]
    latest_parts = [int(p) for p in latest.split('.')]
    
    for i in range(max(len(local_parts), len(latest_parts))):
        lp = local_parts[i] if i < len(local_parts) else 0
        rp = latest_parts[i] if i < len(latest_parts) else 0
        if rp > lp:
            return True, latest
        if lp > rp:
            return False, latest
            
    return False, latest

def start_update_process():
    """Downloads the new version and triggers the self-replacement script."""
    try:
        if not getattr(sys, 'frozen', False):
            logger.warning("Auto-update is only available in the built executable.")
            return False

        current_exe = sys.executable
        new_exe = current_exe + ".new"
        
        # 1. Download the latest EXE
        logger.info(f"Downloading update from {RELEASE_EXE_URL}...")
        response = requests.get(RELEASE_EXE_URL, stream=True, timeout=30)
        if response.status_code != 200:
            logger.error(f"Failed to download update: HTTP {response.status_code}")
            return False
            
        with open(new_exe, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Remove "Mark of the Web" — Windows blocks DLL extraction from internet-downloaded exes
        try:
            zone_file = new_exe + ":Zone.Identifier"
            if os.path.exists(zone_file):
                os.remove(zone_file)
        except Exception:
            pass
        # Also try via command-line (more reliable for ADS removal)
        try:
            subprocess.run(["powershell", "-Command", f'Unblock-File -Path "{new_exe}"'], 
                          capture_output=True, timeout=5)
        except Exception:
            pass
                
        # Plan L: In-Place Update (No External Scripts)
        logger.info("Executing In-Place Swap (Plan L)...")
        try:
            old_exe = current_exe + ".old"
            
            # Clean up previous old file if it exists
            if os.path.exists(old_exe):
                try:
                    os.remove(old_exe)
                except Exception as e:
                    logger.warning(f"Could not remove previous .old file: {e}")
            
            # 1. Rename the currently running executable to free up its name
            # Windows allows renaming open files, but not deleting them.
            os.rename(current_exe, old_exe)
            
            # 2. Put the new executable in the original spot
            os.rename(new_exe, current_exe)
            
            # 3. Aggressively strip PyInstaller environment variables
            # _MEIPASS2 is the main culprit causing child-process DLL crashes.
            env = os.environ.copy()
            for var in ['_MEIPASS', '_MEIPASS2', 'PYI_CHILD_PATH', 'PYTHONHOME', 'PYTHONPATH']:
                env.pop(var, None)
            
            # 4. Launch the new version directly
            logger.info("Launching new executable in detached process...")
            subprocess.Popen([current_exe], env=env, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
            
            # 5. Exit immediately so the new process can run clean
            os._exit(0)
             
        except Exception as e:
            logger.error(f"In-Place update failed: {e}")
            # Try to undo the rename if the swap failed
            try:
                if os.path.exists(old_exe) and not os.path.exists(current_exe):
                    os.rename(old_exe, current_exe)
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return False
