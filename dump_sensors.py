
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.HardwareMonitor import _lhm_worker, _lhm_available
import time

def dump_sensors():
    print(f"LHM Available: {_lhm_available}")
    if not _lhm_available:
        return
        
    _lhm_worker.start(500)
    print("Waiting for sensors to populate...")
    time.sleep(5)
    
    with _lhm_worker._cache_lock:
        print("\n--- AVAILABLE SENSORS ---")
        for key, value in _lhm_worker._cache.items():
            print(f"{key} -> {value}")
    
    _lhm_worker._running = False

if __name__ == "__main__":
    dump_sensors()
