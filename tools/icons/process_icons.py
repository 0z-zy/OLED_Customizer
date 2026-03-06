from PIL import Image
import os

# Resolve project root dynamically (tools/icons/ -> project root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# Source icons — place your raw PNGs in tools/icons/raw/ before running
RAW_DIR = os.path.join(SCRIPT_DIR, "raw")

icons = {
    "cpu_icon.png": os.path.join(RAW_DIR, "cpu_icon.png"),
    "gpu_icon.png": os.path.join(RAW_DIR, "gpu_icon.png"),
    "ram_icon.png": os.path.join(RAW_DIR, "ram_icon.png"),
}

dest_dir = os.path.join(PROJECT_ROOT, "content", "assets", "icons")

for name, path in icons.items():
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        # Resize to 12x12 with nearest neighbor to keep pixel art look
        img = img.resize((12, 12), Image.Resampling.NEAREST)
        
        # Convert to 1-bit for OLED
        # Create black background image first to handle transparency
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3]) # 3 is alpha channel
        bg = bg.convert("1")
        
        save_path = os.path.join(dest_dir, name)
        bg.save(save_path)
        print(f"Saved {save_path}")
    else:
        print(f"Source not found: {path}")
        print(f"  Place your raw icon PNGs in: {RAW_DIR}")
