import json
import os
import logging
import time


def _nowplaying_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "OLED Customizer", "yt_nowplaying.json")

logger = logging.getLogger("OLED Customizer.MediaFallback")


class MediaFallback:
    def __init__(self):
        self.path = _nowplaying_path()

    def read(self):
        try:
            if not os.path.exists(self.path):
                return None

            # 2 kez dene (write sırasında yakalarsak)
            data = None
            for _ in range(2):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    break
                except json.JSONDecodeError:
                    time.sleep(0.05)

            if not isinstance(data, dict):
                return None

            now_ms = int(time.time() * 1000)
            ts = int(data.get("ts") or 0)

            # YT kapalıysa dosya yaşlanır -> fallback KAPAT
            if (now_ms - ts) > 3000:   # 3 saniyeden eskiyse hiç kullanma
                return None

            title = (data.get("title") or "").strip()
            artist = (data.get("artist") or "").strip()
            paused = bool(data.get("paused", False))

            progress = int(data.get("progress_ms") or 0)
            duration = int(data.get("duration_ms") or 0)
            if duration <= 0:
                duration = 1
                progress = 0

            if not title and not artist:
                return None

            return {
                "title": title if title else "YouTube",
                "artist": artist,
                "progress": max(progress, 0),
                "duration": max(duration, 1),
                "paused": paused,
            }
        except Exception:
            return None
