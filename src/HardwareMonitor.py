"""
Hardware Monitor for OLED display.
Uses LibreHardwareMonitor via pythonnet to get CPU/GPU temps.
Includes WMI fallback.
"""
import logging
from time import time
from threading import Thread, Lock
import os

import psutil
from PIL import Image, ImageDraw, ImageFont

from src.image_utils import fetch_content_path

logger = logging.getLogger("OLED Customizer.HardwareMonitor")

# Try to load LibreHardwareMonitor
_lhm_available = False
_computer = None
_update_lock = Lock()

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


def _init_hardware():
    """Initialize hardware monitoring (call once at startup)."""
    global _computer
    if not _lhm_available or _computer is not None:
        return
    
    try:
        _computer = HW.Computer()
        _computer.IsCpuEnabled = True
        _computer.IsGpuEnabled = True
        _computer.IsMemoryEnabled = True
        _computer.Open()
        logger.info("Hardware monitoring initialized")
    except Exception as e:
        logger.error(f"Failed to init hardware monitoring: {e}")


class HardwareMonitor:
    """
    Hardware monitor overlay for OLED display.
    """
    
    def __init__(self, config, timeout=3.0):
        self.config = config
        self.timeout = timeout
        self._last_trigger = 0.0
        
        # Larger font
        self.FONT = ImageFont.truetype(
            font=fetch_content_path("fonts/VerdanaBold.ttf"),
            size=11,
        )
        
        # Load icons
        self.cpu_icon = self._load_icon("cpu_icon.png")
        self.gpu_icon = self._load_icon("gpu_icon.png")
        self.ram_icon = self._load_icon("ram_icon.png")
        
        # Initialize hardware monitoring in background
        Thread(target=_init_hardware, daemon=True).start()
        
        self._wmi = None
        if _wmi_available:
            try:
                self._wmi = wmi.WMI(namespace="root/WMI")
            except:
                pass

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
        """Get value from LHM."""
        if not _lhm_available or _computer is None:
            return None
        
        try:
            with _update_lock:
                # Iterate all hardware
                for hw in _computer.Hardware:
                    # Filter HW type
                    if hw_type.lower() not in str(hw.HardwareType).lower():
                        continue
                        
                    hw.Update()
                    for sensor in hw.Sensors:
                        if sensor_type.lower() not in str(sensor.SensorType).lower():
                            continue
                        if name_contains and name_contains.lower() not in str(sensor.Name).lower():
                            continue
                        if sensor.Value is not None and sensor.Value > 0:
                            return float(sensor.Value)
                            
                    # SubHardware (some GPUs)
                    for sub in hw.SubHardware:
                        sub.Update()
                        for sensor in sub.Sensors:
                            if sensor_type.lower() not in str(sensor.SensorType).lower():
                                continue
                            if name_contains and name_contains.lower() not in str(sensor.Name).lower():
                                continue
                            if sensor.Value is not None and sensor.Value > 0:
                                return float(sensor.Value)
        except:
            pass
        return None

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

        def draw_centered(text, cx, cy):
            bbox = draw.textbbox((0, 0), text, font=self.FONT)
            tw = bbox[2] - bbox[0]
            draw.text((cx + (col_width - tw) / 2, cy), text, font=self.FONT, fill=self.config.primary)

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

        # --- Column 3: RAM ---
        paste_centered(self.ram_icon, c3_x, y_icon)
        draw_centered(f"{ram_used:.1f}G", c3_x, y_text1)
        ram_total = mem.total / (1024**3)
        draw_centered(f"{int(ram_total)}GB", c3_x, y_text2)

        return image
