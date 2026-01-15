"""
ProfileBackup - Backup and restore SteelSeries GG profiles.
Protects your keyboard macros, bindings, and lighting settings.
"""

import os
import shutil
import sqlite3
import logging
from datetime import datetime
from typing import List, Tuple, Optional

logger = logging.getLogger("OLED Customizer.ProfileBackup")

# SteelSeries database paths
PROGRAMDATA = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
SS_BASE = os.path.join(PROGRAMDATA, "SteelSeries", "GG")

DATABASES = {
    "engine": os.path.join(SS_BASE, "apps", "engine", "db", "database.db"),
    "prism": os.path.join(SS_BASE, "apps", "engine", "prism", "db", "database.db"),
    "sonar": os.path.join(SS_BASE, "apps", "sonar", "db", "database.db"),
}


def get_backup_dir() -> str:
    """Get the backup directory path."""
    from src.utils import fetch_app_data_path
    return fetch_app_data_path("backups")


def list_backups() -> List[Tuple[str, str, int]]:
    """
    List all available backups.
    
    Returns:
        List of (backup_name, full_path, file_count) tuples, newest first.
    """
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".db")]
            backups.append((name, path, len(files)))
    
    # Sort by name (which is date), newest first
    backups.sort(reverse=True)
    return backups


def backup_profiles(max_backups: int = 5) -> Optional[str]:
    """
    Backup SteelSeries profile databases.
    
    Args:
        max_backups: Maximum number of backups to keep.
    
    Returns:
        Path to the backup folder, or None if failed.
    """
    # Create backup folder with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_dir = get_backup_dir()
    backup_path = os.path.join(backup_dir, timestamp)
    
    try:
        os.makedirs(backup_path, exist_ok=True)
        
        backed_up = 0
        for name, db_path in DATABASES.items():
            if os.path.exists(db_path):
                dest = os.path.join(backup_path, f"{name}_database.db")
                shutil.copy2(db_path, dest)
                size_mb = os.path.getsize(dest) / 1024 / 1024
                logger.info(f"Backed up {name}: {size_mb:.1f} MB")
                backed_up += 1
        
        if backed_up == 0:
            logger.warning("No databases found to backup")
            os.rmdir(backup_path)
            return None
        
        logger.info(f"Backup complete: {backup_path}")
        
        # Cleanup old backups
        _cleanup_old_backups(max_backups)
        
        return backup_path
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None


def _cleanup_old_backups(max_backups: int):
    """Remove old backups beyond the limit."""
    backups = list_backups()
    while len(backups) > max_backups:
        _, old_path, _ = backups.pop()  # Remove oldest
        try:
            shutil.rmtree(old_path)
            logger.info(f"Removed old backup: {old_path}")
        except Exception as e:
            logger.warning(f"Failed to remove old backup: {e}")


def restore_profiles(backup_path: str) -> bool:
    """
    Restore SteelSeries profiles from a backup.
    
    IMPORTANT: SteelSeries GG must be stopped before restoring!
    
    Args:
        backup_path: Path to the backup folder.
    
    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(backup_path):
        logger.error(f"Backup not found: {backup_path}")
        return False
    
    # Check if GG is running
    from src.utils import is_process_running
    if is_process_running(["SteelSeriesGG.exe", "SteelSeriesEngine3.exe"]):
        logger.error("SteelSeries GG is running! Please close it before restoring.")
        return False
    
    try:
        restored = 0
        for name, db_path in DATABASES.items():
            backup_file = os.path.join(backup_path, f"{name}_database.db")
            if os.path.exists(backup_file):
                # Create parent dirs if needed
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                shutil.copy2(backup_file, db_path)
                logger.info(f"Restored {name} database")
                restored += 1
        
        if restored == 0:
            logger.warning("No database files found in backup")
            return False
        
        logger.info(f"Restore complete! Restored {restored} databases.")
        return True
        
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False


def vacuum_databases() -> Tuple[float, float]:
    """
    Compact SteelSeries databases to reduce size.
    
    IMPORTANT: SteelSeries GG must be stopped!
    
    Returns:
        Tuple of (size_before_mb, size_after_mb).
    """
    from src.utils import is_process_running
    if is_process_running(["SteelSeriesGG.exe", "SteelSeriesEngine3.exe"]):
        logger.error("SteelSeries GG is running! Please close it before compacting.")
        return (0, 0)
    
    size_before = 0
    size_after = 0
    
    for name, db_path in DATABASES.items():
        if not os.path.exists(db_path):
            continue
            
        try:
            before = os.path.getsize(db_path)
            size_before += before
            
            conn = sqlite3.connect(db_path)
            conn.execute("VACUUM")
            conn.close()
            
            after = os.path.getsize(db_path)
            size_after += after
            
            saved = (before - after) / 1024 / 1024
            logger.info(f"Vacuumed {name}: saved {saved:.1f} MB")
            
        except Exception as e:
            logger.error(f"Failed to vacuum {name}: {e}")
    
    return (size_before / 1024 / 1024, size_after / 1024 / 1024)


def get_database_sizes() -> dict:
    """Get current sizes of all databases."""
    sizes = {}
    for name, db_path in DATABASES.items():
        if os.path.exists(db_path):
            sizes[name] = os.path.getsize(db_path) / 1024 / 1024
    return sizes
