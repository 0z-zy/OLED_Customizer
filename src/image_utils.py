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


def convert_to_bitmap(image):
    """
    Convert a PIL mode-"1" image to the SteelSeries binary bitmap.

    PIL's tobytes() already packs 8 pixels/byte MSB-first (rows padded to a
    byte boundary — a non-issue at 128px width), which is exactly the
    GameSense format, so the conversion is a single C call.

    Accepts a pixel sequence (legacy image.getdata() callers) as fallback.
    """
    if hasattr(image, "tobytes"):
        return image.tobytes()

    # Legacy path: sequence of 0/255 pixel values
    res = bytearray()
    for i in range(0, len(image), 8):
        byte = 0
        for j in range(8):
            if image[i + j] > 0:
                byte |= (1 << (7 - j))
        res.append(byte)
    return bytes(res)


# Media source icons are drawn on every rendered frame — load once, not per frame.
_icon_cache = {}


def _get_cached_icon(filename):
    icon = _icon_cache.get(filename)
    if icon is None:
        icon_path = fetch_content_path(f"assets/icons/{filename}")
        icon = Image.open(icon_path).convert("1")
        _icon_cache[filename] = icon
    return icon


def draw_spotify(image, position):
    image.paste(_get_cached_icon("spotify-18.png"), position)


def draw_youtube(image, position):
    image.paste(_get_cached_icon("youtube-18.png"), position)


def draw_generic_media(image, position):
    image.paste(_get_cached_icon("media-18.png"), position)
