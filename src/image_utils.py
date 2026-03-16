import os
import sys
from PIL import Image


def fetch_content_path(relative_path: str) -> str:
    """
    Robustly finds the path to a resource in the 'content' directory.
    Checks:
    1. _MEIPASS (PyInstaller temp folder)
    2. Executable directory
    3. Project root (CWD or script dir)
    """
    # Normalize path separators and remove leading slashes
    relative_path = os.path.normpath(relative_path.lstrip("./\\"))

    possible_bases = []
    
    if getattr(sys, "frozen", False):
        # 1. PyInstaller MEIPASS
        if hasattr(sys, "_MEIPASS"):
            possible_bases.append(sys._MEIPASS)
        # 2. EXE directory
        possible_bases.append(os.path.dirname(sys.executable))
    else:
        # 3. Source directory
        possible_bases.append(os.path.dirname(os.path.dirname(__file__)))
    
    # 4. Final fallback: Current Working Directory
    possible_bases.append(os.getcwd())

    for base in possible_bases:
        full_path = os.path.normpath(os.path.join(base, "content", relative_path))
        if os.path.exists(full_path):
            return full_path
            
    # If not found, return the most likely path anyway (and let the caller fail or use fallback)
    default_base = possible_bases[0] if possible_bases else "."
    return os.path.normpath(os.path.join(default_base, "content", relative_path))


def convert_color(o):
    return 1 if o >= 1 else 0


def convert_to_bitmap(image_data):
    """
    Faster conversion from PIL image data to SteelSeries binary bitmap.
    PIL "1" mode image.getdata() returns 0 or 255.
    """
    res = bytearray()
    # Process 8 pixels at a time into one byte
    for i in range(0, len(image_data), 8):
        byte = 0
        for j in range(8):
            if image_data[i + j] > 0:
                # SteelSeries format: MSB is the leftmost pixel in the 8-pixel block
                byte |= (1 << (7 - j))
        res.append(byte)
    return bytes(res)


def draw_spotify(image, position):
    # content/assets/spotify-18.png bekliyoruz
    icon_path = fetch_content_path("assets/icons/spotify-18.png")
    with Image.open(icon_path).convert("1") as im:
        image.paste(im, position)


def draw_youtube(image, position):
    # content/assets/youtube-18.png bekliyoruz
    icon_path = fetch_content_path("assets/icons/youtube-18.png")
    with Image.open(icon_path).convert("1") as im:
        image.paste(im, position)
def draw_generic_media(image, position):
    # content/assets/media-18.png bekliyoruz
    icon_path = fetch_content_path("assets/icons/media-18.png")
    with Image.open(icon_path).convert("1") as im:
        image.paste(im, position)
