import mmap
import struct
import logging

logger = logging.getLogger("OLED Customizer.FPSMonitor")

class FPSMonitor:
    """
    Reads Game FPS from RTSS (RivaTuner Statistics Server) shared memory.
    """
    
    SHM_NAME = "RTSSSharedMemoryV2"
    SHM_SIZE = 65536
    
    def __init__(self):
        self._mm = None
        
    def _ensure_mmap(self):
        if self._mm:
            return True
        try:
            # mmap.mmap(-1, ...) is for anonymous memory, but on Windows 
            # we can use tagname to open existing named shared memory.
            self._mm = mmap.mmap(-1, self.SHM_SIZE, tagname=self.SHM_NAME, access=mmap.ACCESS_READ)
            return True
        except Exception:
            self._mm = None
            return False

    def get_fps(self) -> int:
        """
        Get the current average FPS from the active 3D application in RTSS.
        """
        if not self._ensure_mmap():
            return 0
            
        try:
            self._mm.seek(0)
            header_data = self._mm.read(48)
            
            # RTSS_SHARED_MEMORY_HEADER
            # DWORD dwSignature ('RTSS')
            # DWORD dwVersion
            # DWORD dwAppEntryOffset
            # DWORD dwAppEntrySize
            # DWORD dwAppPropsOffset (not used here)
            # DWORD dwAppPropsSize (not used here)
            
            sig, ver, app_off, app_size = struct.unpack("<IIII", header_data[:16])
            
            if sig != 0x53535452: # 'RTSS'
                return 0
                
            # The number of app entries is usually at offset 20
            app_count = struct.unpack("<I", header_data[24:28])[0]
            
            for i in range(app_count):
                offset = app_off + i * app_size
                self._mm.seek(offset)
                app_data = self._mm.read(app_size)
                
                # RTSS_SHARED_MEMORY_APP_ENTRY
                # DWORD dwProcessID
                # TCHAR szName[260]
                # ...
                # DWORD dwStatFrameAvg (offset 304 in common V2 versions)
                
                pid = struct.unpack("<I", app_data[:4])[0]
                if pid != 0:
                    # In newer RTSS, dwStatFrameAvg is at offset 304.
                    # It's an integer representing FPS * 10 or similar? 
                    # Actually, usually it's just the average FPS.
                    # For common versions:
                    # Stat flags are at 296
                    # StatFrameAvg is at 304
                    fps = struct.unpack("<I", app_data[304:308])[0]
                    
                    # If it's a very large number, it might be weird. 
                    # RTSS sometimes stores it as fixed point.
                    if fps > 10000: # Probably fixed point or noise
                         return 0
                         
                    return fps
                    
        except Exception as e:
            logger.debug(f"Error reading RTSS FPS: {e}")
            self._mm = None # Force re-open next time
            
        return 0

# Test
if __name__ == "__main__":
    import time
    mon = FPSMonitor()
    while True:
        print(f"FPS: {mon.get_fps()}")
        time.sleep(1)
