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
            timeout=urllib3.Timeout(connect=0.5, read=1.0),
            retries=False
        )
        
        # Thread lock to prevent concurrent sends
        import threading
        self._send_lock = threading.Lock()
        
        # Error back-off (escalating: 2s → 5s → 10s)
        self._consecutive_errors = 0
        self._backoff_until = 0
        self._backoff_level = 0          # 0=2s, 1=5s, 2=10s
        self._BACKOFF_DURATIONS = [2.0, 5.0, 10.0]
        self._RESET_THRESHOLD = 10       # Force re-register after this many consecutive errors
        self._is_resetting = False      # Prevent overlapping resets
        
        # Pre-allocate static headers to reduce object churn
        self._static_headers = {
            "Content-Type": "application/json",
            "Connection": "keep-alive"
        }
        
        # Frame counter for periodic manual GC collection
        self._frames_sent = 0
        
        self.retrieve_address()

    def retrieve_address(self, retries=None):
        """
        Locate coreProps.json and register with the GameSense API.
        If retries is None, loops forever (used for startup).
        Otherwise attempts specified number of retries before giving up.
        """
        attempt = 0
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
                attempt += 1
                if retries is not None and attempt >= retries:
                    logger.error("Failed to connect/register to SteelSeries GameSense API after %d attempts: %s", attempt, e)
                    return None
                    
                logger.error("Could not connect/register to SteelSeries GameSense API (%s). Retry in 5s...", e)
                sleep(5)

    def reset(self):
        """Invalidate current connection and force re-registration."""
        if self._is_resetting:
            return
        self._is_resetting = True
        try:
            logger.info("Resetting SteelSeries connection...")
            self.address = ""
            # Limit retries during resets to avoid blocking the main thread forever
            self.retrieve_address(retries=2)
        finally:
            self._is_resetting = False

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
                # Proceed but DON'T reset error counter yet — wait for success
                if now - self._backoff_until > 0.1: # Only log once per backoff
                   logger.debug("Back-off expired, testing SteelSeries API connection...")

        # Minimize object creation: encode JSON once outside the loop
        body = dumps(data).encode('utf-8')
        url = self.address + endpoint

        if self._send_lock.acquire(timeout=0.5):
            try:
                headers = self._static_headers.copy()
                headers["Content-Length"] = str(len(body))
                
                response = self._http.request(
                    "POST",
                    url,
                    body=body,
                    headers=headers
                )
                
                # IMPORTANT: In urllib3, you must read the response data to 
                # release the connection back to the pool.
                resp_data = response.data
                
                if response.status == 200:
                    self._consecutive_errors = 0
                    self._backoff_level = 0
                else:
                    logger.debug("SteelSeries API error %d: %s", response.status, resp_data.decode('utf-8', 'ignore'))
                    self._consecutive_errors += 1
            except Exception as e:
                self._consecutive_errors += 1
                logger.debug("SteelSeries API transport error: %s", e)
            finally:
                self._send_lock.release()
        else:
            logger.warning("SteelSeries API send lock TIMEOUT (0.5s)")

        # Auto-recovery: if errors are persistent, force a full re-registration
        if self._consecutive_errors >= self._RESET_THRESHOLD:
            logger.warning("Persistent API errors (%d), forcing re-registration...", self._consecutive_errors)
            # Reset counter so we don't loop reset() if it fails internally
            self._consecutive_errors = 0
            self._backoff_level = 0
            try:
                self.reset()
            except Exception as e:
                logger.error("Auto-reset failed: %s", e)
        # Standard backoff with escalation
        elif self._consecutive_errors >= 5:
            # Clamp level
            idx = min(self._backoff_level, len(self._BACKOFF_DURATIONS) - 1)
            duration = self._BACKOFF_DURATIONS[idx]
            self._backoff_until = time() + duration
            # Increment level for next time (escalation)
            self._backoff_level += 1
            logger.warning("Too many API errors (%d), backing off for %.0fs", self._consecutive_errors, duration)
