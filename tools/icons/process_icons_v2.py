from PIL import Image
import os

# Resolve project root dynamically (tools/icons/ -> project root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Source icons — place your raw PNGs in tools/icons/raw/ before running
RAW_DIR = os.path.join(SCRIPT_DIR, "raw")

icons = {
    "speaker_high_v2.png": os.path.join(RAW_DIR, "speaker_vol_high.png"),
    "speaker_mid_v2.png": os.path.join(RAW_DIR, "speaker_vol_mid.png"),
    "speaker_low_v2.png": os.path.join(RAW_DIR, "speaker_vol_low.png"),
    "speaker_mute_v2.png": os.path.join(RAW_DIR, "speaker_vol_mute.png"),
}

dest_dir = os.path.join(PROJECT_ROOT, "content", "assets")

for name, path in icons.items():
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        # Resize to 12x12
        img = img.resize((12, 12), Image.Resampling.NEAREST)
        
        # Convert to 1-bit
        # Create black background 
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3]) 
        bg = bg.convert("1")
        
        save_path = os.path.join(dest_dir, name)
        bg.save(save_path)
        print(f"Saved {save_path}")
    else:
        print(f"Source not found: {path}")
        print(f"  Place your raw icon PNGs in: {RAW_DIR}")
