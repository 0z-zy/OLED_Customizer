from json import loads
from time import sleep, time
from os import environ, path
import logging
import requests

GAME = "OLED_CUSTOMIZER_V3"
GAME_DISPLAY_NAME = "OLED Customizer"
AUTHOR = "0z-zy"
EVENT = "UPDATE"

logger = logging.getLogger("OLED Customizer.SteelSeriesAPI")


class SteelSeriesAPI:
    def __init__(self):
        programdata = environ.get("PROGRAMDATA") or r"C:\ProgramData"
        self.coreprops_paths = [
            path.join(programdata, "SteelSeries", "SteelSeries Engine 3", "coreProps.json"),
            path.join(programdata, "SteelSeries", "SteelSeries GG", "coreProps.json"),
        ]
        self.address = ""
        self.retrieve_address()

    def retrieve_address(self):
        while True:
            try:
                coreprops = None
                for p in self.coreprops_paths:
                    if path.exists(p):
                        coreprops = p
                        break

                if not coreprops:
                    raise OSError("coreProps.json not found (Engine/GG not running?)")

                with open(coreprops, "r", encoding="utf-8") as f:
                    data = loads(f.readline())
                    self.address = "http://" + data["address"]

                # Clean start: remove and re-register
                self.remove_game()
                self.register_game()
                self.bind_game_event()

                logger.info("Found local address API : %s", self.address)
                return self.address
            except Exception as e:
                logger.error("Could not connect/register to SteelSeries GameSense API (%s). Retry in 5s...", e)
                sleep(5)

    def reset(self):
        """Invalidate current connection and force re-registration."""
        logger.info("Resetting SteelSeries connection...")
        self.address = ""
        self.retrieve_address()

    def bind_game_event(self):
        # Apex 7 Pro OLED = 128x40 (640 byte)
        dummy_128x40 = [0 for _ in range(640)]

        self.send_data("/bind_game_event", {
            "game": GAME,
            "event": EVENT,
            "value_optional": True,
            "handlers": [
                {
                    "device-type": "screened-128x40",
                    "mode": "screen",
                    "datas": [
                        {"has-text": False, "image-data": dummy_128x40}
                    ]
                }
            ]
        })

        logger.info("Binding game event (128x40 only)")

    def send_frame(self, image_128x40):
        if not isinstance(image_128x40, list):
            raise ValueError("Image must be a list")

        img40 = image_128x40[:640] + [0] * max(0, 640 - len(image_128x40))

        self.send_data("/game_event", {
            "game": GAME,
            "event": EVENT,
            "data": {
                "frame": {
                    "image-data-128x40": img40
                }
            }
        })

    def send_rgb(self, r, g, b):
        """Send RGB color to all peripheral zones."""
        self.send_data("/game_event", {
            "game": GAME,
            "event": EVENT,
            "data": {
                "value": 100, # Dummy value to trigger handlers if needed
                "frame": {
                    "rgb-per-key": [r, g, b] * 150 # Large enough array for most keyboards
                }
            }
        })

    def remove_game(self):
        try:
            self.send_data("/remove_game", {"game": GAME})
        except:
            pass

    def register_game(self):
        self.send_data("/game_metadata", {
            "game": GAME,
            "game_display_name": GAME_DISPLAY_NAME,
            "developer": AUTHOR,
            "deinitialize_timer_length_ms": 60000 # 1 minute keep-alive
        })

    def send_data(self, endpoint, data):
        try:
            response = requests.post(
                self.address + endpoint,
                json=data,
                headers={"Connection": "close"},
                timeout=0.25
            )
            if response.status_code != 200:
                logger.debug("SteelSeries API error %d: %s", response.status_code, response.text)
        except Exception as e:
            # Silently ignore timeouts/connection errors during normal operation
            pass
