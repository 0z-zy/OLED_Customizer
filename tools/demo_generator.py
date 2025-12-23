import os
import sys
import time
from PIL import Image

# Add root to sys.path to import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.Config import Config
from src.Timer import Timer
from src.SpotifyPlayer import SpotifyPlayer
from src.UserPreferences import UserPreferences

def generate_gif(frames, filename, duration=100):
    dest = os.path.join("content", "demos", filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    
    # Take images and convert to RGB/L for GIF compatibility if needed, 
    # but "1" mode also works if converted to "P" or "L"
    gif_frames = [f.convert("P") for f in frames]
    gif_frames[0].save(
        dest,
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration,
        loop=0
    )
    print(f"[OK] Generated {dest}")

def create_clock_demo(style_name, filename):
    config = Config()
    # Mock preferences for Timer
    timer = Timer(config, date_format=24, display_seconds=True, use_turkish_days=False, style=style_name)
    
    frames = []
    # Generate 60 frames (approx 6 seconds at 10fps)
    for i in range(20):
        # We can't easily mock time inside Timer without changing Timer.py
        # But we can just capture frames. 
        # To show movement in analog/seconds, we can wait a bit or just accept it's a static capture if time doesn't change fast enough.
        # Actually, Timer uses localtime(), so it will show current time.
        frames.append(timer.get_image())
        time.sleep(0.05) # Small sleep to maybe see a second change
        
    generate_gif(frames, filename)

def create_player_demo(source, title, artist, filename):
    config = Config()
    prefs = UserPreferences()
    prefs.preferences["extended_font"] = True
    
    player = SpotifyPlayer(config, prefs, fps=10)
    player.update_song(title, artist, song_position=120000, song_duration=240000, paused=False, source=source)
    
    frames = []
    for i in range(40):
        frames.append(player.next_step())
    
    generate_gif(frames, filename)

if __name__ == "__main__":
    print("Generating Demos...")
    
    # 1. Clock Styles
    create_clock_demo("Analog", "demo_clock_analog.gif")
    create_clock_demo("Big Timer", "demo_clock_big.gif")
    create_clock_demo("Date Focused", "demo_clock_date.gif")
    
    # 2. Player Sources
    create_player_demo("youtube", "Lofi Girl - lofi hip hop radio", "Lofi Girl", "demo_player_youtube.gif")
    create_player_demo("generic", "Windows Media Player", "System Audio", "demo_player_generic.gif")
    
    print("Done!")
