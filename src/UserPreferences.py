from os import path, makedirs, replace
from json import loads, dumps
from copy import deepcopy
from threading import Thread

import logging
import ctypes

from src.utils import fetch_app_data_path

logger = logging.getLogger("OLED Customizer")

class UserPreferences:
    DEFAULT = {
        "spotify_enabled": False,
        "spotify_client_id": "",
        "spotify_client_secret": "",
        "spotify_redirect_uri": "",
        "local_port": 2408,
        "date_format": 12,
        "display_seconds": True,
        "timer_threshold": 2,
        "spotify_fetch_delay": 2,
        "extended_font": True,
        "display_timer": True,
        "display_player": True,
        "display_hw_monitor": False,
        "debug_enabled": False,
        "use_turkish_days": False,
        "clock_style": "Standard",
        "hotkey_monitor": "Key.insert",
        "hotkey_mute": "Key.pause",
        "rgb_enabled": False,
        "rgb_color": [0, 212, 170],
        "primary": 1,
        "secondary": 0,
        "scrollbar_padding": 2,
        "text_padding_left": 30,
        "width": 128,
        "height": 40,
        "auto_launch_gg": False,
        "player_style": "Standard",
        "hw_polling_interval": 1000,
        "show_game_fps": False,
        "selected_gpu": "Auto",
        "hotkey_calculator": "Key.insert",
        "hotkey_mute_2": "",
        "discord_client_id": "",
        "discord_client_secret": "",
        "discord_access_token": "",
        "headset_hid_sync_enabled": False,
        "discord_local_port": 8888,
        "show_headset_battery": False,
        "show_album_art": False
    }

    def __init__(self):
        self.valid = True
        self.preferences = deepcopy(self.DEFAULT)
        self.config_path = fetch_app_data_path("config.json")
        logger.info("Preferences path : " + self.config_path)

    def load_preferences(self) -> bool:
        self.valid = True

        try:
            with open(self.config_path, "r") as file:
                raw = file.read()
        except FileNotFoundError:
            logger.info("No preferences found, created default preferences")
            self.save_preferences()
            return True

        try:
            parsed = loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("config.json root must be an object")
            self.preferences = parsed
        except Exception as e:
            # Recover instead of refusing to run: keep the broken file for
            # inspection, reset to defaults, and warn without blocking any thread.
            logger.error("Corrupt config.json (%s) — resetting to defaults", e)
            try:
                replace(self.config_path, self.config_path + ".bad")
            except OSError:
                pass
            self.preferences = deepcopy(self.DEFAULT)
            self.save_preferences()
            self._warn_corrupt_config(str(e))
            return True

        modified = False
        for key, value in self.DEFAULT.items():
            if key not in self.preferences:
                self.preferences[key] = value
                modified = True

        if modified:
            self.save_preferences()
        return True

    @staticmethod
    def _warn_corrupt_config(detail):
        def _show():
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Your config.json was corrupt and has been reset to defaults.\n"
                    "The old file was kept as config.json.bad.\n\n" + detail,
                    "OLED Customizer - Settings Reset",
                    0x30,  # MB_ICONWARNING
                )
            except Exception:
                pass
        Thread(target=_show, daemon=True).start()

    def save_preferences(self):
        # Ensure the directory exists before writing
        makedirs(path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as file:
            file.write(dumps(self.preferences, indent=4))

    def get_preference(self, key):
        return self.preferences.get(key)
