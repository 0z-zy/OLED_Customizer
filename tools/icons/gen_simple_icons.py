from PIL import Image, ImageDraw
import os

def create_icon(name, draw_func):
    img = Image.new('1', (12, 12), color=0)  # Black background
    draw = ImageDraw.Draw(img)
    draw_func(draw)
    
    # Invert for OLED (White on Black usually, but 1-bit logic depends on display code)
    # Assuming code pastes with mask or handles 1 as white.
    # Actually code uses `image.paste(icon, ...)`
    # Let's make background black (0) and shape white (1)
    
    path = f"content/assets/{name}.png"
    img.save(path)
    print(f"Saved {path}")

def draw_cpu(draw):
    # Restore: Square chip with pins (User liked this)
    draw.rectangle((2, 2, 9, 9), outline=1, fill=0)
    # Pins
    draw.point([(1,3), (1,5), (1,7), (1,9)], fill=1) # Left
    draw.point([(10,3), (10,5), (10,7), (10,9)], fill=1) # Right
    draw.point([(3,1), (5,1), (7,1), (9,1)], fill=1) # Top
    draw.point([(3,10), (5,10), (7,10), (9,10)], fill=1) # Bottom
    # Inner dot
    draw.rectangle((4, 4, 7, 7), fill=1)

def draw_gpu(draw):
    # Redesign: Clearly a graphics card
    # Main PCB Board
    draw.rectangle((1, 2, 10, 8), outline=1, fill=0)
    # PCIe Connector (Bottom)
    draw.line((3, 9, 8, 9), fill=1)
    draw.line((3, 10, 8, 10), fill=1)
    # Fan (Circle in middle)
    draw.point((5,5), fill=1)
    draw.point((6,5), fill=1)
    draw.point((5,6), fill=1)
    draw.point((6,6), fill=1)

def draw_ram(draw):
    # A simple chip (Horizontal rect with legs)
    draw.rectangle((2, 3, 9, 8), outline=1, fill=0)
    # Legs
    draw.point([(3,9), (5,9), (7,9)], fill=1)
    draw.point([(3,2), (5,2), (7,2)], fill=1)


if __name__ == "__main__":
    os.makedirs("content/assets", exist_ok=True)
    create_icon("cpu_icon", draw_cpu)
    create_icon("gpu_icon", draw_gpu)
    create_icon("ram_icon", draw_ram)
