from PIL import Image
import os

def make_transparent(img):
    img = img.convert("RGBA")
    datas = img.getdata()
    
    # Logic: Make all black pixels transparent
    # The icon is neon blue on black.
    target_bg = (0, 0, 0)
    tolerance = 80 # Higher tolerance to catch compression on black
    
    new_data = []
    for item in datas:
        # Check distance from black
        if all(abs(item[i] - target_bg[i]) < tolerance for i in range(3)):
            new_data.append((255, 255, 255, 0)) # Transparent
        else:
            new_data.append(item)
            
    img.putdata(new_data)
    return img

def convert_icon():
    source = "content/assets/icon.png"
    target_ico = "content/assets/icon.ico"
    target_png = "content/assets/icon.png"

    if not os.path.exists(source):
        print(f"Source not found: {source}")
        return

    img = Image.open(source)
    img = make_transparent(img)
    
    # Save as PNG
    img.save(target_png)
    
    # Save as ICO (containing multiple sizes)
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(target_ico, format='ICO', sizes=sizes)
    print(f"Icon converted with transparency: {target_ico}")

if __name__ == "__main__":
    convert_icon()
