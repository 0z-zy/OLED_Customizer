
import os
import sys
import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import time
import psutil # Needed for HwMon mock? No, we override it.

# Add project root to path
sys.path.append(r"c:\Users\super\Desktop\Code Stuff\OLED Customizer")

from src.Config import Config
from src.SpotifyPlayer import SpotifyPlayer
from src.Timer import Timer
from src.HardwareMonitor import HardwareMonitor
# from src.volume import VolumeOverlay # We simulate volume manually to avoid COM deps

# Mock preferences
class MockPreferences:
    def get_preference(self, key):
        defaults = {
            'extended_font': True,
            'date_format': 12,
            'display_seconds': True
        }
        return defaults.get(key)

class MockHardwareMonitor(HardwareMonitor):
    def __init__(self, config):
        # Skip init thread in base class
        # Skip init thread in base class
        self.config = config
        self.FONT = ImageFont.truetype(
            font=r"c:\Users\super\Desktop\Code Stuff\OLED Customizer\content\fonts\VerdanaBold.ttf",
            size=11,
        )
        self.cpu_icon = self._load_icon("cpu_icon.png")
        self.gpu_icon = self._load_icon("gpu_icon.png")
        self.ram_icon = self._load_icon("ram_icon.png")

    def _load_icon(self, filename):
        path = fr"c:\Users\super\Desktop\Code Stuff\OLED Customizer\content\assets\icons\{filename}"
        if os.path.exists(path):
            return Image.open(path).convert("1")
        return None

    def get_image(self):
        w, h = self.config.width, self.config.height
        image = Image.new("1", (w, h), color=self.config.secondary)
        draw = ImageDraw.Draw(image)
        
        # MOCKED VALUES
        cpu_temp = 58
        cpu_usage = 32
        gpu_temp = 45
        gpu_load = 12
        ram_used = 10.5
        
        # --- Layout Constants ---
        col_width = w // 3
        c1_x = 0
        c2_x = col_width
        c3_x = col_width * 2
        
        y_icon = 0
        y_text1 = 13
        y_text2 = 26

        def draw_centered(text, cx, cy):
            bbox = draw.textbbox((0, 0), text, font=self.FONT)
            tw = bbox[2] - bbox[0]
            draw.text((cx + (col_width - tw) / 2, cy), text, font=self.FONT, fill=self.config.primary)

        def paste_centered(icon, cx, cy):
            if icon:
                ix = cx + (col_width - 12) // 2
                image.paste(icon, (int(ix), cy))

        # --- Column 1: CPU ---
        paste_centered(self.cpu_icon, c1_x, y_icon)
        draw_centered(f"{cpu_temp}°", c1_x, y_text1)
        draw_centered(f"{cpu_usage}%", c1_x, y_text2)

        # --- Column 2: GPU ---
        paste_centered(self.gpu_icon, c2_x, y_icon)
        draw_centered(f"{gpu_temp}°", c2_x, y_text1)
        draw_centered(f"{gpu_load}%", c2_x, y_text2)

        # --- Column 3: RAM ---
        paste_centered(self.ram_icon, c3_x, y_icon)
        draw_centered(f"{ram_used:.1f}G", c3_x, y_text1)
        draw_centered(f"32GB", c3_x, y_text2)

        return image

def save_gif(frames, filename, fps):
    print(f"saving {len(frames)} frames to {filename}")
    try:
        with imageio.get_writer(filename, mode='I', duration=1/fps, loop=0) as writer:
            for frame in frames:
                writer.append_data(np.array(frame))
        print(f"Done! {filename} created.")
    except Exception as e:
        print(f"Error saving gif: {e}")

def generate_demos():
    print("Generating demo GIFs...")
    
    fps = 10
    config = Config()
    config.width = 128
    config.height = 40
    prefs = MockPreferences()
    
    player = SpotifyPlayer(config, prefs, fps)
    hw_mon = MockHardwareMonitor(config)
    timer = Timer(config, 12, True)
    
    # 1. Player Demo
    print("Generating demo_player.gif...")
    frames = []
    player.update_song("BITTERSUITE", "Billie Eilish", 45000, 240000, paused=False, source="spotify")
    for _ in range(fps * 5): # 5 seconds
        img = player.next_step()
        frames.append(img.convert("RGBA"))
    save_gif(frames, 'demo_player.gif', fps)

    # 2. Volume Demo
    print("Generating demo_volume.gif...")
    frames = []
    # Ramp up volume
    for step in range(15):
        vol = int(step * 5) + 10
        img = Image.new("1", (128, 40), 0)
        draw = ImageDraw.Draw(img)
        
        # Determine icon based on volume
        icon_name = "speaker_low.png"
        if vol > 33: icon_name = "speaker_mid.png"
        if vol > 66: icon_name = "speaker_high.png"

        icon_path = fr"c:\Users\super\Desktop\Code Stuff\OLED Customizer\content\assets\{icon_name}"
        if os.path.exists(icon_path):
             icon = Image.open(icon_path).convert("1")
             img.paste(icon, (2, 14))
        
        # Bar
        draw.rectangle((18, 16, 124, 24), outline=1)
        fill_w = int((124 - 18 - 2) * (vol / 100))
        draw.rectangle((20, 18, 20 + fill_w, 22), fill=1)
        frames.append(img.convert("RGBA"))
    
    # Hold final frame
    for _ in range(fps):
        frames.append(frames[-1])
    save_gif(frames, 'demo_volume.gif', fps)

    # 3. Hardware Monitor
    print("Generating demo_hw_monitor.gif...")
    frames = []
    hw_img = hw_mon.get_image()
    # Flicker effect simulating update? No, just static is fine or slightly changing values if we mocked randomness
    # Let's keep it static but distinct
    for _ in range(fps * 3):
        frames.append(hw_img.convert("RGBA"))
    save_gif(frames, 'demo_hw_monitor.gif', fps)

    # 4. Clock
    print("Generating demo_clock.gif...")
    frames = []
    # To make it animated, we should show the seconds ticking.
    # Since the real Timer uses localtime(), we'll mock it or just let it run
    # but 3 seconds at 10fps might not show much change.
    # Let's mock the time progression manually for the demo.
    import datetime
    base_time = datetime.datetime.now()
    for i in range(fps * 5): # 5 seconds
        current = base_time + datetime.timedelta(seconds=i/fps)
        # We need a way to pass this mocked time to Timer. 
        # Let's just monkeypatch localtime for a moment or modify Timer.
        # Simplest: override get_current_time for this loop
        def mocked_get():
            seconds = ":%02d" % current.second if timer.display_seconds else ""
            hour_24 = current.hour
            am_pm = "AM" if hour_24 < 12 else "PM"
            if timer.date_format == 12:
                time_text = current.strftime("%I:%M") + seconds + f" {am_pm}"
            else:
                time_text = current.strftime("%H:%M") + seconds + f" {am_pm}"
            date_text = current.strftime("%a %d/%m/%Y")
            return time_text, date_text
        
        timer.get_current_time = mocked_get
        img = timer.get_image()
        frames.append(img.convert("RGBA"))
    save_gif(frames, 'demo_clock.gif', fps)

if __name__ == "__main__":
    generate_demos()
