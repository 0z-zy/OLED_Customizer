from json import loads
from time import sleep, time
import gc
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
        # Use persistent Session with connection pooling to reduce object churn
        # This prevents GC crashes during frequent API calls
        from urllib3.util.retry import Retry
        from requests.adapters import HTTPAdapter
        
        self._session = requests.Session()
        self._session.headers.update({"Connection": "keep-alive"})
        
        # Limit pool size and disable retries to minimize object creation
        adapter = HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=Retry(total=0)
        )
        self._session.mount("http://", adapter)
        
        # Thread lock to prevent concurrent sends
        self._send_lock = __import__('threading').Lock()
        
        # Error back-off: stop hammering API when it's struggling
        self._consecutive_errors = 0
        self._backoff_until = 0  # timestamp - don't send until this time
        
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
        if not isinstance(image_128x40, (list, bytes, bytearray)):
            raise ValueError("Image must be a list or bytes")

        # Convert to list for JSON - pad/trim to exactly 640 bytes
        img_list = list(image_128x40[:640])
        img40 = img_list + [0] * max(0, 640 - len(img_list))

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
            "deinitialize_timer_length_ms": 900000  # 15 minutes keep-alive (was 60s)
        })

    def heartbeat(self):
        """Send a lightweight heartbeat to keep the game registered with SteelSeries GG."""
        try:
            self.send_data("/game_heartbeat", {"game": GAME})
        except Exception:
            pass

    def send_data(self, endpoint, data):
        # Error back-off: if we've had too many errors, wait before retrying
        if self._consecutive_errors >= 5:
            now = time()
            if now < self._backoff_until:
                return  # Still in back-off period, skip this send
            else:
                # Back-off expired, reset and try again
                logger.info("Back-off expired, resuming API calls...")
                self._consecutive_errors = 0

        # Use lock to prevent concurrent sends (reduces object churn/GC crashes)
        with self._send_lock:
            response = None
            try:
                response = self._session.post(
                    self.address + endpoint,
                    json=data,
                    timeout=0.5
                )
                if response.status_code != 200:
                    logger.debug("SteelSeries API error %d: %s", response.status_code, response.text)
                    self._consecutive_errors += 1
                else:
                    # Success - reset error counter
                    self._consecutive_errors = 0
            except (OSError, RuntimeError) as e:
                # COM/threading errors that can occur during GC
                self._consecutive_errors += 1
            except Exception as e:
                # Timeouts/connection errors
                self._consecutive_errors += 1
            finally:
                # IMPORTANT: Always close response to free memory
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

                # If we hit the error threshold, start back-off
                if self._consecutive_errors >= 5:
                    self._backoff_until = time() + 2.0  # Wait 2 seconds
                    logger.warning("Too many API errors (%d), backing off for 2s", self._consecutive_errors)
