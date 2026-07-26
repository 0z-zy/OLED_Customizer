
import ctypes
from threading import Thread, Lock
import time
import logging
import os
import sys

logger = logging.getLogger("OLED Customizer.FPSMonitor")

# --- PresentMon DLL Interface ---
class PresentMonExitCodes:
    STATUS_OK = 0
    GENERAL_ERROR = 1000
    PRIVILIGIES_ERROR = 1007

# We use double precision for the data from the DLL
class FPSMonitor:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FPSMonitor, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self._fps_value = 0
        self._running = False
        self._lib = None
        # Generation token: a worker exits when its generation is stale, so a
        # fast stop()->start() cycle can't resurrect the old worker thread.
        self._worker_gen = 0
        # Serializes all DLL calls (worker vs start/stop from other threads)
        self._dll_lock = Lock()
        self._initialized = True
        
        # Determine DLL path
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        self._dll_path = os.path.join(base_dir, "src", "lib", "PresentMon.dll")

        # Lazy: an ETW capture of every process is not free. The owner calls
        # start()/stop() based on the show_game_fps preference.

    def start(self):
        if self._running: return
        
        if not os.path.exists(self._dll_path):
            logger.error(f"FPSMonitor: DLL not found at {self._dll_path}")
            return

        try:
            if self._lib is None:
                self._lib = ctypes.CDLL(self._dll_path)

            # Setup argtypes/restypes for PresentMon.dll
            # int64_t StartEventRecording(int64_t pid, int64_t max_samples)
            self._lib.StartEventRecording.restype = ctypes.c_int64
            self._lib.StartEventRecording.argtypes = [ctypes.c_int64, ctypes.c_int64]
            
            # int64_t StopEventRecording()
            self._lib.StopEventRecording.restype = ctypes.c_int64
            
            # int64_t GetCurrentData(int64_t num_samples, double* out_data, double* out_times, int64_t* out_size)
            # The DLL expects: FPS, FlipRate, DeltaReady, DeltaDisplayed, TimeTaken, ScreenTime (6 doubles per sample)
            self._lib.GetCurrentData.restype = ctypes.c_int64
            self._lib.GetCurrentData.argtypes = [
                ctypes.c_int64, 
                ctypes.POINTER(ctypes.c_double), 
                ctypes.POINTER(ctypes.c_double), 
                ctypes.POINTER(ctypes.c_int64)
            ]

            # Start recording (pid 0 = all processes)
            with self._dll_lock:
                res = self._lib.StartEventRecording(0, 86400)
            if res != PresentMonExitCodes.STATUS_OK:
                logger.error(f"FPSMonitor: Failed to start recording (Error {res})")
                return

            self._running = True
            self._worker_gen += 1
            Thread(target=self._worker_loop, args=(self._worker_gen,),
                   daemon=True, name="FPS-DLL-Worker").start()
            logger.info("FPSMonitor: Native PresentMon logic started")
            
        except Exception as e:
            logger.error(f"FPSMonitor: Failed to load/init DLL: {e}")

    def _worker_loop(self, gen):
        # Local buffers for GetCurrentData
        num_samples = 1
        data_buf = (ctypes.c_double * (num_samples * 6))()
        time_buf = (ctypes.c_double * num_samples)()
        size_buf = (ctypes.c_int64 * 1)()

        while self._running and gen == self._worker_gen:
            try:
                with self._dll_lock:
                    res = self._lib.GetCurrentData(num_samples, data_buf, time_buf, size_buf)
                if res == PresentMonExitCodes.STATUS_OK and size_buf[0] > 0:
                    # Index 0 is FPS
                    with self._lock:
                        self._fps_value = int(data_buf[0])
                else:
                    with self._lock:
                        self._fps_value = 0
            except Exception as e:
                logger.debug("FPS worker error: %s", e)
            time.sleep(0.5)

    def get_fps(self) -> int:
        with self._lock:
            return self._fps_value

    def stop(self):
        self._running = False
        self._worker_gen += 1  # invalidate any live worker immediately
        if self._lib:
            try:
                with self._dll_lock:
                    self._lib.StopEventRecording()
            except Exception: pass
