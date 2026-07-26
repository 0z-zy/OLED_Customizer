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


def list_backups() -> List[Tuple[str, str, int, float]]:
    """
    List all available backups.
    
    Returns:
        List of (backup_name, full_path, file_count, mtime) tuples, newest first.
    """
    backup_dir = get_backup_dir()
    if not os.path.exists(backup_dir):
        return []
    
    backups = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".db")]
            mtime = os.path.getmtime(path)
            backups.append((name, path, len(files), mtime))
    
    # Sort by modification time, newest first
    backups.sort(key=lambda x: x[3], reverse=True)
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
        _, old_path, _, _ = backups.pop()  # Remove oldest (name, path, count, mtime)
        try:
            shutil.rmtree(old_path)
            logger.info(f"Removed old backup: {old_path}")
        except Exception as e:
            logger.warning(f"Failed to remove old backup: {e}")


def restore_profiles(backup_path: str) -> bool:
    """
    Restore SteelSeries profiles from a backup.
    
    SAFETY: Creates a backup of current databases before restoring!
    Note: Caller should ensure SteelSeries GG is closed before calling.
    
    Args:
        backup_path: Path to the backup folder.
    
    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(backup_path):
        logger.error(f"Backup not found: {backup_path}")
        return False
    
    try:
        # SAFETY: Create a backup of current databases BEFORE restoring
        logger.info("Creating safety backup before restore...")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safety_backup_dir = os.path.join(get_backup_dir(), f"pre_restore_{timestamp}")
        os.makedirs(safety_backup_dir, exist_ok=True)
        
        for name, db_path in DATABASES.items():
            if os.path.exists(db_path):
                dest = os.path.join(safety_backup_dir, f"{name}_database.db")
                shutil.copy2(db_path, dest)
                logger.info(f"Safety backup: {name} -> {dest}")
        
        logger.info(f"Safety backup created: {safety_backup_dir}")
        
        # Clean up WAL/SHM files (these contain uncommitted transactions)
        for name, db_path in DATABASES.items():
            wal_path = db_path + "-wal"
            shm_path = db_path + "-shm"
            if os.path.exists(wal_path):
                try:
                    os.remove(wal_path)
                    logger.info(f"Removed WAL file: {wal_path}")
                except Exception as e:
                    logger.warning(f"Could not remove WAL file {wal_path}: {e}")
            if os.path.exists(shm_path):
                try:
                    os.remove(shm_path)
                    logger.info(f"Removed SHM file: {shm_path}")
                except Exception as e:
                    logger.warning(f"Could not remove SHM file {shm_path}: {e}")
        
        # Now restore from backup
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
        logger.info(f"If something went wrong, you can restore from: {safety_backup_dir}")
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


def delete_backup(backup_path: str) -> bool:
    """Delete a backup folder."""
    logger.info(f"Backend: Attempting to delete backup at: {backup_path}")
    if not os.path.exists(backup_path):
        logger.error(f"Backend: Backup path does not exist: {backup_path}")
        return False
    try:
        shutil.rmtree(backup_path)
        logger.info(f"Backend: Deleted backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Backend: Failed to delete backup {backup_path}: {e}")
        return False


def duplicate_backup(backup_path: str) -> Optional[str]:
    """Duplicate a backup folder with a '_copy' suffix."""
    if not os.path.exists(backup_path):
        return None
    
    try:
        # Create new name
        base_dir = os.path.dirname(backup_path)
        base_name = os.path.basename(backup_path)
        
        # If it already ends in a timestamp or something, just append copy
        new_name = base_name + "_copy"
        new_path = os.path.join(base_dir, new_name)
        
        # Handle collision
        counter = 1
        while os.path.exists(new_path):
            new_path = os.path.join(base_dir, f"{new_name}_{counter}")
            counter += 1
            
        shutil.copytree(backup_path, new_path)
        logger.info(f"Duplicated backup: {backup_path} -> {new_path}")
        return new_path
    except Exception as e:
        logger.error(f"Failed to duplicate backup {backup_path}: {e}")
        return None
