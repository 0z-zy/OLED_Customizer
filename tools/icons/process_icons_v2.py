from PIL import Image
import os

icons = {
    "speaker_high_v2.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/speaker_vol_high_1766346598423.png",
    "speaker_mid_v2.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/speaker_vol_mid_1766346610736.png",
    "speaker_low_v2.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/speaker_vol_low_1766346623800.png",
    "speaker_mute_v2.png": "C:/Users/super/.gemini/antigravity/brain/ccd7851e-5478-4625-a915-bf6f4324f406/speaker_vol_mute_1766346634771.png"
}

dest_dir = "content/assets/"

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
