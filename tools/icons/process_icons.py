from PIL import Image
import os

icons = {
    "cpu_icon.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/cpu_icon_1766345694860.png",
    "gpu_icon.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/gpu_icon_1766345708452.png",
    "ram_icon.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/ram_icon_1766345721484.png"
}

dest_dir = "content/assets/"

for name, path in icons.items():
    if os.path.exists(path):
        img = Image.open(path).convert("RGBA")
        # Resize to 12x12 with nearest neighbor to keep pixel art look
        img = img.resize((12, 12), Image.Resampling.NEAREST)
        
        # Convert to 1-bit for OLED
        # Create white background image first to handle transparency
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3]) # 3 is alpha channel
        bg = bg.convert("1")
        
        save_path = os.path.join(dest_dir, name)
        bg.save(save_path)
        print(f"Saved {save_path}")
    else:
        print(f"Source not found: {path}")
