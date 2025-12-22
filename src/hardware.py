import logging
from time import time

import psutil
from PIL import Image, ImageDraw, ImageFont

try:
    import wmi
except ImportError:
    wmi = None

from src.image_utils import fetch_content_path

logger = logging.getLogger("OLED Customizer.HardwareOverlay")


class HardwareOverlay:
    FONT = ImageFont.truetype(
        font=fetch_content_path("fonts/MunroSmall.ttf"),
        size=10,
    )

    def __init__(self, config, timeout=2.0):
        """
        timeout: INS'e bastıktan sonra overlay kaç saniye ekranda kalsın
        """
        self.config = config
        self.timeout = timeout
        self._last_trigger = 0.0

    def trigger(self):
        """INS'e basıldığında çağrılacak."""
        self._last_trigger = time()

    def should_display(self) -> bool:
        """Overlay şu an görünmeli mi?"""
        return (time() - self._last_trigger) < self.timeout

    def _read_cpu(self):
        usage = int(round(psutil.cpu_percent(interval=None)))
        temp = None

        # CPU sıcaklığı: OpenHardwareMonitor WMI dene
        if wmi is not None:
            try:
                c = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                for sensor in c.Sensor():
                    if sensor.SensorType == "Temperature" and "CPU Package" in sensor.Name:
                        temp = int(round(sensor.Value))
                        break
            except Exception as e:
                logger.debug("CPU temp via OpenHardwareMonitor failed: %s", e)

        return usage, temp

    def _read_gpu(self):
        temp = None

        if wmi is not None:
            try:
                c = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                for sensor in c.Sensor():
                    if sensor.SensorType == "Temperature" and "GPU Core" in sensor.Name:
                        temp = int(round(sensor.Value))
                        break
            except Exception as e:
                logger.debug("GPU temp via OpenHardwareMonitor failed: %s", e)

        return temp

    def _read_ram(self):
        mem = psutil.virtual_memory()
        return int(round(mem.percent))

    def get_image(self):
        """
        128x40 OLED için basit metin overlay:

        CPU  55C 23%
        GPU  60C
        RAM  30%
        """
        w, h = self.config.width, self.config.height
        image = Image.new("1", (w, h), color=self.config.secondary)
        draw = ImageDraw.Draw(image)

        cpu_usage, cpu_temp = self._read_cpu()
        gpu_temp = self._read_gpu()
        ram_usage = self._read_ram()

        # Sıcaklık sembolü yerine 'C' kullanıyoruz (font kare yapmasın diye)
        cpu_temp_str = f"{cpu_temp}C" if cpu_temp is not None else "--C"
        gpu_temp_str = f"{gpu_temp}C" if gpu_temp is not None else "--C"

        line1 = f"CPU {cpu_temp_str} {cpu_usage}%"
        line2 = f"GPU {gpu_temp_str}"
        line3 = f"RAM {ram_usage}%"

        x = 2
        y = 4
        line_height = 12

        draw.text((x, y), line1, font=self.FONT, fill=self.config.primary, anchor="lm")
        y += line_height
        draw.text((x, y), line2, font=self.FONT, fill=self.config.primary, anchor="lm")
        y += line_height
        draw.text((x, y), line3, font=self.FONT, fill=self.config.primary, anchor="lm")

        return image