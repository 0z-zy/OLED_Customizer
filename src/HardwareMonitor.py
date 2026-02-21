"""
Hardware Monitor for OLED display.
Uses LibreHardwareMonitor via pythonnet to get CPU/GPU temps.
Includes WMI fallback.

Thread-safety: LHM runs in dedicated worker thread to avoid COM threading issues.
"""
import logging
from time import time, sleep
from threading import Thread, Lock
import os

import psutil
from PIL import Image, ImageDraw, ImageFont

from src.image_utils import fetch_content_path
from src.fps_monitor import FPSMonitor

logger = logging.getLogger("OLED Customizer.HardwareMonitor")

# Try to load LibreHardwareMonitor
_lhm_available = False

# WMI Fallback
try:
    import wmi
    _wmi_available = True
except ImportError:
    _wmi = None
    _wmi_available = False

try:
    # First check if admin
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        logger.warning("Not running as Admin - LHM sensors might fail")

    import HardwareMonitor.Hardware as HW
    _lhm_available = True
    logger.info("LibreHardwareMonitor loaded successfully")
except Exception as e:
    logger.warning(f"LibreHardwareMonitor not available: {e}")


class _LHMWorker:
    """
    Dedicated worker thread that owns all LibreHardwareMonitor COM objects.
    Main thread reads from cached values, never touching LHM directly.
    This fixes COM threading crashes (RPC_E_WRONG_THREAD).
    """
    
    def __init__(self):
        self._cache = {}
        self._cache_lock = Lock()
        self._running = False
        self._computer = None
        self._polling_interval = 1000 # Default 1s
        
    def start(self, interval=1000):
        self._polling_interval = interval
        if self._running or not _lhm_available:
            return
        self._running = True
        Thread(target=self._worker_loop, daemon=True, name="LHM-Worker").start()
        
    def _worker_loop(self):
        """Runs in dedicated thread - owns all COM objects."""
        try:
            # Initialize COM for this thread
            import ctypes
            ctypes.windll.ole32.CoInitialize(0)
        except Exception:
            pass
            
        try:
            self._computer = HW.Computer()
            self._computer.IsCpuEnabled = True
            self._computer.IsGpuEnabled = True
            self._computer.IsMemoryEnabled = True
            self._computer.Open()
            logger.info("LHM Worker: Hardware monitoring initialized")
        except Exception as e:
            logger.error(f"LHM Worker: Failed to init: {e}")
            self._running = False
            return
            
        # Main update loop - update sensors every 500ms
        while self._running:
            try:
                new_cache = {}
                
                for hw in self._computer.Hardware:
                    hw_type = str(hw.HardwareType).lower()
                    hw_name = str(hw.Name)
                    hw.Update()
                    
                    # logger.debug(f"LHM: Processing HW: {hw_name} ({hw_type})")
                    
                    for sensor in hw.Sensors:
                        if sensor.Value is not None:
                            # Use tuple key: (hw_type, hw_name, sensor_type, sensor_name)
                            key = (hw_type, hw_name, str(sensor.SensorType).lower(), str(sensor.Name).lower())
                            new_cache[key] = float(sensor.Value)
                            
                    # SubHardware (some GPUs)
                    for sub in hw.SubHardware:
                        sub.Update()
                        for sensor in sub.Sensors:
                            if sensor.Value is not None:
                                key = (hw_type, hw_name, str(sensor.SensorType).lower(), str(sensor.Name).lower())
                                new_cache[key] = float(sensor.Value)
                
                with self._cache_lock:
                    self._cache = new_cache
                    
            except Exception as e:
                logger.debug(f"LHM Worker update error: {e}")
                
            sleep(self._polling_interval / 1000.0)  # Dynamic interval
            
    def get_sensor(self, hw_type, sensor_type, name_contains=None, hw_name=None):
        """Thread-safe read from cache."""
        with self._cache_lock:
            for (hw, hn, st, name), value in self._cache.items():
                if hw_type.lower() not in hw:
                    continue
                if hw_name and hw_name.lower() != "auto" and hw_name.lower() not in hn.lower():
                    continue
                if sensor_type.lower() not in st:
                    continue
                if name_contains and name_contains.lower() not in name:
                    continue
                return value
        return None

    def get_available_gpus(self):
        """Return list of detected GPU names."""
        gpus = set()
        with self._cache_lock:
            for (hw, hn, st, name) in self._cache.keys():
                if "gpu" in hw:
                    gpus.add(hn)
        return sorted(list(gpus))


# Global worker instance
_lhm_worker = _LHMWorker()


class HardwareMonitor:
    """
    Hardware monitor overlay for OLED display.
    """
    
    def __init__(self, config, preferences, timeout=3.0):
        self.config = config
        self.preferences = preferences
        self.timeout = timeout
        self._last_trigger = 0.0
        
        # Instance-level font (not shared across threads)
        self.FONT = ImageFont.truetype(
            font=fetch_content_path("fonts/VerdanaBold.ttf"),
            size=11,
        )
        
        # Load icons
        self.cpu_icon = self._load_icon("cpu_icon.png")
        self.gpu_icon = self._load_icon("gpu_icon.png")
        self.ram_icon = self._load_icon("ram_icon.png")
        
        # Start the LHM worker (idempotent)
        interval = preferences.get_preference("hw_polling_interval") or 1000
        _lhm_worker.start(interval)
        
        # FPS Monitor
        self.fps_monitor = FPSMonitor()
        self.show_fps = bool(preferences.get_preference("show_game_fps"))
        
        self._wmi = None
        if _wmi_available:
            try:
                self._wmi = wmi.WMI(namespace="root/WMI")
            except:
                pass

    def update_preferences(self, preferences):
        """Update settings dynamically."""
        self.show_fps = bool(preferences.get_preference("show_game_fps"))
        interval = preferences.get_preference("hw_polling_interval") or 1000
        _lhm_worker._polling_interval = interval
        # If worker is not running, start it
        if not _lhm_worker._running:
            _lhm_worker.start(interval)

    def _load_icon(self, filename):
        try:
            path = fetch_content_path(f"assets/icons/{filename}")
            if os.path.exists(path):
                return Image.open(path).convert("1")
        except Exception as e:
            logger.warning(f"Failed to load icon {filename}: {e}")
        return None

    def trigger(self):
        self._last_trigger = time()

    def should_display(self) -> bool:
        return (time() - self._last_trigger) < self.timeout

    def _get_lhm_sensor(self, hw_type, sensor_type, name_contains=None):
        """Get value from LHM worker cache (thread-safe)."""
        selected_gpu = self.preferences.get_preference("selected_gpu") or "Auto"
        return _lhm_worker.get_sensor(hw_type, sensor_type, name_contains, hw_name=selected_gpu if hw_type.lower() == "gpu" else None)

    def get_available_gpus(self):
        return _lhm_worker.get_available_gpus()

    def _get_wmi_cpu_temp(self):
        """Fallback CPU temp from WMI."""
        if not self._wmi:
            return None
        try:
            temps = self._wmi.MSAcpi_ThermalZoneTemperature()
            for t in temps:
                c = (t.CurrentTemperature / 10.0) - 273.15
                if c > 0:
                    return c
        except:
            pass
        return None

    def get_image(self):
        w, h = self.config.width, self.config.height
        image = Image.new("1", (w, h), color=self.config.secondary)
        draw = ImageDraw.Draw(image)

        # --- Data Gathering ---
        # 1. CPU
        cpu_temp = self._get_lhm_sensor("Cpu", "Temperature", "Tctl")
        if not cpu_temp:
            cpu_temp = self._get_lhm_sensor("Cpu", "Temperature", "Package")
        if not cpu_temp:
            cpu_temp = self._get_lhm_sensor("Cpu", "Temperature", "Core")
        if not cpu_temp:
            cpu_temp = self._get_wmi_cpu_temp()
        cpu_usage = int(round(psutil.cpu_percent(interval=None)))
        
        # 2. GPU
        gpu_temp = self._get_lhm_sensor("Gpu", "Temperature", "Core")
        if not gpu_temp:
             gpu_temp = self._get_lhm_sensor("Gpu", "Temperature", "GPU")
        gpu_load = self._get_lhm_sensor("Gpu", "Load", "Core")
        if not gpu_load:
            gpu_load = self._get_lhm_sensor("Gpu", "Load", "GPU")
            
        # 3. RAM
        mem = psutil.virtual_memory()
        ram_used = mem.used / (1024**3)
        ram_percent = mem.percent
        
        # 4. FPS (Native ETW / LHM Fallback)
        fps = 0
        show_fps = bool(self.preferences.get_preference("show_game_fps"))
        if show_fps:
            fps = self.fps_monitor.get_fps()
            if fps <= 0:
                # Try LHM fallback (some GPUs or LHM plugins provide this)
                lhm_fps = self._get_lhm_sensor("Gpu", "Factor", "Frame Rate")
                if not lhm_fps:
                     lhm_fps = self._get_lhm_sensor("Gpu", "Data", "Frame Rate")
                if lhm_fps:
                    fps = int(lhm_fps)

        # --- Layout Constants ---
        # 3 Columns: 0-42, 43-85, 86-128
        col_width = w // 3
        c1_x = 0
        c2_x = col_width
        c3_x = col_width * 2
        
        # Rows (Y positions)
        y_icon = 0
        y_text1 = 13
        y_text2 = 26

        def draw_centered(text, cx, cy, font=None):
            f = font or self.FONT
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
            draw.text((cx + (col_width - tw) / 2, cy), text, font=f, fill=self.config.primary)

        def paste_centered(icon, cx, cy):
            if icon:
                # Icon is 12x12
                ix = cx + (col_width - 12) // 2
                image.paste(icon, (int(ix), cy))

        # --- Column 1: CPU ---
        paste_centered(self.cpu_icon, c1_x, y_icon)
        t_val = f"{int(cpu_temp)}°" if cpu_temp else "--"
        draw_centered(t_val, c1_x, y_text1)
        draw_centered(f"{cpu_usage}%", c1_x, y_text2)

        # --- Column 2: GPU ---
        paste_centered(self.gpu_icon, c2_x, y_icon)
        t_val = f"{int(gpu_temp)}°" if gpu_temp else "--"
        draw_centered(t_val, c2_x, y_text1)
        draw_centered(f"{int(gpu_load) if gpu_load else 0}%", c2_x, y_text2)

        # --- Column 3: RAM / FPS ---
        if show_fps:
            # If FPS toggle is ON, always prioritize showing FPS or Idle
            paste_centered(self.ram_icon, c3_x, y_icon)
            draw_centered(f"{ram_used:.1f}G", c3_x, y_text1)
            if fps > 0:
                # For high FPS (3 digits), shorten the label to avoid overlap
                val_text = f"{int(fps)}"
                if fps < 100:
                    val_text += " FPS"
                draw_centered(val_text, c3_x, y_text2)
            else:
                draw_centered("Idle", c3_x, y_text2)
        else:
            # Default RAM display (RAM Used / Total)
            paste_centered(self.ram_icon, c3_x, y_icon)
            draw_centered(f"{ram_used:.1f}G", c3_x, y_text1)
            ram_total = mem.total / (1024**3)
            draw_centered(f"{int(ram_total)}GB", c3_x, y_text2)

        return image
