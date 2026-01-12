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
                
        # 2. Create the batch script for replacement
        # This script waits for the main app to close, replaces the file, and restarts it.
        batch_script = current_exe + "_update.bat"
        with open(batch_script, 'w') as f:
            f.write(f'@echo off\n')
            f.write(f'taskkill /F /PID {os.getpid()} >nul 2>&1\n')
            f.write(f'timeout /t 2 /nobreak >nul\n') # Wait for app to close
            f.write(f'del "{current_exe}"\n')
            f.write(f'move /Y "{new_exe}" "{current_exe}"\n')
            f.write(f'start "" "{current_exe}"\n')
            f.write(f'del "%~f0"\n') # Self-delete batch file
            
        # 3. Launch the batch script and exit
        logger.info("Triggering update script...")
        subprocess.Popen([batch_script], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        os._exit(0)
        
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return False
