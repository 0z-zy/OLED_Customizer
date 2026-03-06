from PIL import Image
import os

# Option B from the first set
opt_b = [
    "010100010100",
    "110110110110",
    "110110110110",
    "100010100010",
    "111110111110",
    "100010100010",
    "111110111110",
    "100010100010",
    "110110110110",
    "110110110110",
    "010100010100",
    "000000000000",
]

def update_icon():
    dest = "content/assets/icons/ram_icon.png"
    img = Image.new("1", (12, 12), 0)
    pixels = img.load()
    
    for y, row in enumerate(opt_b):
        for x, char in enumerate(row):
            if char == "1":
                pixels[x, y] = 1
                
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.save(dest)
    print(f"Updated RAM icon with Option B at: {dest}")

if __name__ == "__main__":
    update_icon()
