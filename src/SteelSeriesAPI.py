from json import loads, dumps
from time import sleep, time
import gc
from os import environ, path
import logging
import urllib3

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
        
        # Use urllib3 PoolManager directly for maximum performance and minimal object churn.
        # requests.Session creates many heavy objects (Headers, CaseInsensitiveDict, etc.)
        # for every single request, which can lead to GC crashes at 10+ FPS.
        self._http = urllib3.PoolManager(
            num_pools=1,
            headers={"Content-Type": "application/json", "Connection": "keep-alive"},
            timeout=urllib3.Timeout(connect=0.1, read=0.5),
            retries=False
        )
        
        # Thread lock to prevent concurrent sends
        import threading
        self._send_lock = threading.Lock()
        
        # Error back-off
        self._consecutive_errors = 0
        self._backoff_until = 0
        
        # Frame counter for periodic manual GC collection
        self._frames_sent = 0
        
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
                "value": 100, 
                "frame": {
                    "rgb-per-key": [r, g, b] * 150 
                }
            }
        })

    def remove_game(self):
        try:
            self.send_data("/remove_game", {"game": GAME})
        except Exception:
            pass

    def register_game(self):
        self.send_data("/game_metadata", {
            "game": GAME,
            "game_display_name": GAME_DISPLAY_NAME,
            "developer": AUTHOR,
            "deinitialize_timer_length_ms": 60000 
        })

    def heartbeat(self):
        """Send a lightweight heartbeat to keep the game registered."""
        try:
            self.send_data("/game_heartbeat", {"game": GAME})
        except Exception:
            pass

    def send_data(self, endpoint, data):
        # Error back-off check
        if self._consecutive_errors >= 5:
            now = time()
            if now < self._backoff_until:
                return
            else:
                logger.info("Back-off expired, resuming API calls...")
                self._consecutive_errors = 0

        # Minimize object creation: encode JSON once outside the loop
        body = dumps(data).encode('utf-8')
        url = self.address + endpoint

        with self._send_lock:
            try:
                response = self._http.request(
                    "POST",
                    url,
                    body=body,
                    headers={
                        "Content-Length": str(len(body)),
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status != 200:
                    logger.debug("SteelSeries API error %d: %s", response.status, response.data.decode('utf-8', 'ignore'))
                    self._consecutive_errors += 1
                else:
                    self._consecutive_errors = 0
                
                # IMPORTANT: In urllib3, you must ensure the response data is read 
                # (already done by .data) so the connection can be returned to the pool.
            except Exception as e:
                self._consecutive_errors += 1
                # logger.debug("SteelSeries API Transport Error: %s", e)

        # If we hit error threshold, start back-off
        if self._consecutive_errors >= 5:
            self._backoff_until = time() + 2.0
            logger.warning("Too many API errors (%d), backing off for 2s", self._consecutive_errors)
