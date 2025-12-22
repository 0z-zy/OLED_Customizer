import os
import sys
from PIL import Image


def fetch_content_path(relative_path: str) -> str:
    """
    Kaynak dosya yolunu döndürür.

    EXE içinden:
        <_MEIPASS>/content/<relative_path without ./ >
    Normal python:
        <proje_kökü>/content/<relative_path without ./ >
    """

    # relative_path başındaki ./ veya \ gibi şeyleri temizle
    relative_path = relative_path.lstrip("./\\")  # "fonts/..." veya "assets/..." gibi kalır

    if getattr(sys, "frozen", False):
        # PyInstaller exe içi
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        content_base = os.path.join(base_path, "content")
    else:
        # Normal python: src/ klasöründen proje köküne çık
        base_dir = os.path.dirname(os.path.dirname(__file__))  # .../SpotifyLinke
        content_base = os.path.join(base_dir, "content")

    return os.path.join(content_base, relative_path)


def convert_color(o):
    return 1 if o >= 1 else 0


def convert_to_bitmap(image_data):
    res = []
    for i in range(0, len(image_data), 8):
        byte = 0
        for j in range(7, -1, -1):
            byte += convert_color(image_data[i + j]) << (7 - j)
        res.append(byte)

    return res


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
