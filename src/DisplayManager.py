from threading import Thread
from queue import Queue, Empty
from time import sleep, time
import logging

from src.SpotifyAPI import SpotifyAPI
from src.SpotifyPlayer import SpotifyPlayer
from src.SteelSeriesAPI import SteelSeriesAPI
from src.Timer import Timer
from src.Calculator import Calculator
from src.volume import VolumeOverlay
from src.image_utils import convert_to_bitmap
from src.UserPreferences import UserPreferences
from src.Systray import run_systray_async
from src.WindowsMedia import WindowsMedia
from src.HardwareMonitor import HardwareMonitor
from src.ExtensionReceiver import ExtensionReceiver
from src.utils import is_process_running, find_steelseries_gg_path, launch_process
import asyncio

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

logger = logging.getLogger("OLED Customizer")


class State:
    SHOW_CLOCK = 0
    SHOW_PLAYER = 1
    SHOW_CALCULATOR = 2


class DisplayManager:
    def __init__(self, config, fps):
        self.config = config
        self.fps = fps
        self.state = State.SHOW_CLOCK

        self.enabled = True
        self.display_clock = True
        self.display_player = True
        self.display_hw_monitor = False

        self.user_preferences = UserPreferences()
        self.user_preferences.load_preferences()  # Load saved preferences FIRST
        self.timer = Timer(
            config,
            self.user_preferences.get_preference("date_format"),
            self.user_preferences.get_preference("display_seconds"),
            self.user_preferences.get_preference("use_turkish_days"),
            self.user_preferences.get_preference("clock_style"),
        )

        self.calculator = Calculator(config)
        self._calculator_active = False  # True when OLED is showing the calculator

        run_systray_async(self)

        self.player = SpotifyPlayer(config, self.user_preferences, fps)
        
        # Only initialize Spotify API if enabled in preferences
        self.spotify_enabled = self.user_preferences.get_preference("spotify_enabled")
        if self.spotify_enabled:
            self.spotify_api = SpotifyAPI(self.user_preferences)
        else:
            self.spotify_api = None
        
        self.steelseries_api = SteelSeriesAPI()

        self.volume_overlay = VolumeOverlay(config)
        self.hardware_monitor = HardwareMonitor(config, self.user_preferences)
        self.extension_receiver = ExtensionReceiver(port=8888)
        self.extension_receiver.start()

        # Setup keyboard listener for INS key and Global Hotkeys
        if keyboard:
            self._listener = None
            self._hotkey_listener = None

        if keyboard:
            self._listener = None
            self.key_monitor_val = None
            self.key_mute_val = None
            self.key_calculator_val = None
            # Track whether Ctrl is currently held for combo hotkeys (Ctrl+Insert)
            self._ctrl_held = False

            def on_press(key):
                try:
                    # Track Ctrl modifier
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        self._ctrl_held = True

                    # --- Calculator toggle: Ctrl + calculator key ---
                    if self._ctrl_held and key == self.key_calculator_val:
                        self._ctrl_held = False  # Consume the modifier to prevent stickiness
                        self._calculator_active = not self._calculator_active
                        if self._calculator_active:
                            self.calculator.clear()  # Fresh start every time
                            logger.info("Calculator activated")
                        else:
                            logger.info("Calculator deactivated")
                        return

                    # --- Calculator control keys (non-numpad) ---
                    # Numpad digits/operators are caught by the raw Windows hook below.
                    # Here we only handle Esc, Enter, Backspace, Delete.
                    if self._calculator_active:
                        if key == keyboard.Key.esc:
                            self._calculator_active = False
                            logger.info("Calculator exited via Escape")
                            return
                        if key == keyboard.Key.enter:
                            self.calculator.key_input("enter")
                            return
                        if key == keyboard.Key.backspace:
                            self.calculator.key_input("backspace")
                            return
                        if key == keyboard.Key.delete:
                            self.calculator.key_input("delete")
                            return

                    # --- Normal hotkeys (always active) ---
                    if key == self.key_monitor_val:
                        self.hardware_monitor.trigger()
                    elif key == self.key_mute_val:
                        logger.info("Mute key pressed - Toggling Mute")
                        self.volume_overlay.toggle_mic_mute()
                except Exception as e:
                    logger.error(f"Hotkey error: {e}")

            def on_release(key):
                try:
                    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                        self._ctrl_held = False
                except Exception:
                    pass

            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.daemon = True
            self._listener.start()
            logger.info("Keyboard listener started")

            # Start the raw Windows hook for numpad suppression
            Thread(target=self._numpad_hook_loop, daemon=True, name="Numpad-Hook").start()
        else:
            logger.warning("pynput not available, keyboard features disabled")

        # Windows Media (SMTC) - runs in background thread
        self.windows_media = WindowsMedia()
        self._smtc_data = None
        self._smtc_lock = __import__('threading').Lock()
        Thread(target=self._poll_smtc_loop, daemon=True).start()

        now_ms = int(time() * 1000)

        # polling timers
        self._last_spotify_poll_ms = now_ms
        self._last_yt_poll_ms = now_ms

        self._yt_poll_ms = 200

        # SOURCE STATE
        self._spotify_last_seen_ms = 0
        self._spotify_last_playing_ms = 0
        self._spotify_paused = True

        self._yt_last_seen_ms = 0
        self._yt_last_playing_ms = 0
        self._yt_paused = True

        # toleranslar (flicker kesmek için)
        # SIFIRLANDI: Paused olduğu an saate dönmesi için bekleme süreleri kaldırıldı.
        # Geri eklendi: Ancak polling gecikmesi yüzünden olan flicker'ı engellemek için.
        # Bu değer PAUSE basıldığında devreye girmez (explicit check var), 
        # sadece VERİ GELMEDİĞİNDE "hala çalıyor varsay" süresidir.
        self._spotify_hold_playing_ms = 3000   
        self._yt_hold_playing_ms = 3000        

        # gg flicker azalt
        self._last_sent_frame = None
        self._gg_was_running = True
        self._last_rgb_send_ms = 0

        # STICKY SOURCE logic
        self._extension_last_data_ms = 0
        self._extension_lock_seconds = 5
        
        self.auto_launch_gg = False
        self._last_launch_attempt = 0
        self._last_frame_sent_time = 0
        self._last_heartbeat_time = 0  # Heartbeat to keep game registered

        # Spotify worker thread (single persistent thread instead of spawning new ones)
        self._spotify_queue = Queue(maxsize=1)
        Thread(target=self._spotify_worker_loop, daemon=True, name="Spotify-Worker").start()
        
        self.load_preferences()

    # ------------------------------------------------------------------
    # Raw Windows hook for numpad key suppression
    # ------------------------------------------------------------------

    def _numpad_hook_loop(self):
        """
        Installs a low-level Windows keyboard hook (WH_KEYBOARD_LL) via ctypes
        to intercept and suppress numpad keys when calculator mode is active.

        CRITICAL: Uses proper 64-bit types. On x64 Windows, LRESULT/LPARAM/WPARAM
        are all 8 bytes. Using 4-byte c_long would corrupt the stack.
        """
        try:
            import ctypes
            from ctypes import wintypes, POINTER, Structure, byref

            # Use WinDLL with use_last_error for proper error reporting
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            # ---- Constants ----
            WH_KEYBOARD_LL = 13
            HC_ACTION = 0
            WM_KEYDOWN = 0x0100
            WM_SYSKEYDOWN = 0x0104

            # Numpad VK codes (96..111) + VK_OEM_COMMA (188) + VK_OEM_PERIOD (190)
            NUMPAD_VKS = set(range(96, 112))
            NUMPAD_VKS.add(188)
            NUMPAD_VKS.add(190)

            NUMPAD_OP_MAP = {
                107: "+", 109: "-", 106: "*", 111: "/",
                110: ".", 108: ",",  # VK_SEPARATOR for European locales
                188: ",",  # VK_OEM_COMMA
                190: ".",  # VK_OEM_PERIOD
            }

            # ---- Struct for the hook data ----
            class KBDLLHOOKSTRUCT(Structure):
                _fields_ = [
                    ("vkCode",      wintypes.DWORD),
                    ("scanCode",    wintypes.DWORD),
                    ("flags",       wintypes.DWORD),
                    ("time",        wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            # ---- 64-bit safe callback type ----
            # On x64: LRESULT = c_longlong, WPARAM = c_ulonglong, LPARAM = c_longlong
            LRESULT = wintypes.LPARAM   # c_longlong on 64-bit
            HOOKPROC = ctypes.CFUNCTYPE(
                LRESULT,                # return type (8 bytes on x64)
                ctypes.c_int,           # nCode
                wintypes.WPARAM,        # wParam
                wintypes.LPARAM,        # lParam
            )

            # ---- Set proper function signatures ----
            kernel32.GetModuleHandleW.restype = ctypes.c_void_p
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD
            ]

            user32.CallNextHookEx.restype = LRESULT
            user32.CallNextHookEx.argtypes = [
                ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
            ]

            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

            user32.GetMessageW.argtypes = [
                POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
            ]
            user32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]

            # ---- The hook callback ----
            @HOOKPROC
            def _hook_callback(nCode, wParam, lParam):
                try:
                    if nCode == HC_ACTION and self._calculator_active:
                        # Read VK code and flags directly from memory at lParam address
                        # KBDLLHOOKSTRUCT layout: vkCode(4) scanCode(4) flags(4) ...
                        addr = lParam & 0xFFFFFFFFFFFFFFFF  # ensure unsigned
                        vk = ctypes.c_uint32.from_address(addr).value
                        flags = ctypes.c_uint32.from_address(addr + 8).value

                        is_numpad = vk in NUMPAD_VKS
                        is_numpad_enter = (vk == 13 and (flags & 0x01))

                        if is_numpad or is_numpad_enter:
                            # Feed calculator on key-DOWN only
                            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                                if 96 <= vk <= 105:
                                    self.calculator.key_input(str(vk - 96))
                                elif vk in NUMPAD_OP_MAP:
                                    self.calculator.key_input(NUMPAD_OP_MAP[vk])
                                elif is_numpad_enter:
                                    self.calculator.key_input("enter")

                            return LRESULT(1).value  # SUPPRESS
                except Exception:
                    pass  # Never let an exception escape the hook callback

                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # ---- Install ----
            # Must keep callback reference alive (prevent GC)
            self._numpad_hook_proc = _hook_callback

            hmod = kernel32.GetModuleHandleW(None)
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_callback, hmod, 0)

            if not hook:
                err = ctypes.get_last_error()
                logger.error(f"SetWindowsHookExW failed (error {err})")
                return

            logger.info("Numpad suppression hook installed OK")

            # ---- Message pump (required to keep LL hook alive) ----
            msg = wintypes.MSG()
            while user32.GetMessageW(byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

            user32.UnhookWindowsHookEx(hook)
            logger.info("Numpad hook removed")

        except Exception as e:
            # This thread is non-critical — never crash the app
            logger.error(f"Numpad hook thread failed: {e}", exc_info=True)

    # ------------------------------------------------------------------

    def load_preferences(self):
        self.user_preferences.load_preferences()
        self.update_preferences()

    def update_preferences(self):
        self.fetch_delay = max(
            int(self.user_preferences.get_preference("spotify_fetch_delay")),
            1 / self.fps,
        )
        self.timer_threshold = (
            max(int(self.user_preferences.get_preference("timer_threshold")), 0) * 1000
        )

        self.display_clock = self.user_preferences.get_preference("display_timer")
        self.display_player = self.user_preferences.get_preference("display_player")
        self.display_hw_monitor = self.user_preferences.get_preference("display_hw_monitor")

        # Sync Layout constants
        self.config.scrollbar_padding = int(self.user_preferences.get_preference("scrollbar_padding") or 2)
        self.config.text_padding_left = int(self.user_preferences.get_preference("text_padding_left") or 30)

        if hasattr(self.timer, "set_display_seconds"):
            self.timer.set_display_seconds(self.user_preferences.get_preference("display_seconds"))
        if hasattr(self.timer, "set_date_format"):
            self.timer.set_date_format(self.user_preferences.get_preference("date_format"))
        if hasattr(self.timer, "set_use_turkish_days"):
            self.timer.set_use_turkish_days(self.user_preferences.get_preference("use_turkish_days"))
        if hasattr(self.timer, "set_style"):
            self.timer.set_style(self.user_preferences.get_preference("clock_style"))
            
        if hasattr(self.player, "set_style"):
            self.player.set_style(self.user_preferences.get_preference("player_style"))

        if hasattr(self, "hardware_monitor"):
            self.hardware_monitor.update_preferences(self.user_preferences)

        # Hotkeys
        self.key_monitor_val = self._parse_key(self.user_preferences.get_preference("hotkey_monitor"))
        self.key_mute_val = self._parse_key(self.user_preferences.get_preference("hotkey_mute"))
        self.key_calculator_val = self._parse_key(self.user_preferences.get_preference("hotkey_calculator"))
        logger.info(f"Hotkeys bound: Monitor={self.key_monitor_val}, Mute={self.key_mute_val}, Calculator={self.key_calculator_val}")
        
        self.auto_launch_gg = self.user_preferences.get_preference("auto_launch_gg")

        self._spotify_poll_ms = max(250, int(self.fetch_delay * 1000))
        
        # Reload Spotify credentials if they changed (only if Spotify is enabled)
        if hasattr(self, "spotify_api") and self.spotify_api:
            changed = self.spotify_api.reload_config()
            # If credentials changed, force a re-fetch with prompt
            if changed:
                logger.info("Credentials changed, triggering re-auth...")
                Thread(target=self.spotify_api.fetch_token, args=(True,), daemon=True).start()
            
            # If not ready (missing tokens) but config didn't change, we do NOTHING directly here.
            # The user must fix the config in the settings window to trigger the 'changed' path.
            # OR we could silently try to fetch if prompt_user=False? No, let's keep it clean.

    def _parse_key(self, key_str):
        if not key_str or not keyboard:
            return None
        
        try:
            # Handle "Key.insert", "Key.f1" etc.
            if key_str.startswith("Key."):
                attr = key_str.split("Key.")[1]
                return getattr(keyboard.Key, attr, None)
            
            # Handle single chars "a", "1"
            if len(key_str) == 1:
                return keyboard.KeyCode.from_char(key_str)
                
            # Handle codes "<65>"
            if key_str.startswith("<") and key_str.endswith(">"):
                code = int(key_str[1:-1])
                return keyboard.KeyCode.from_vk(code)
                
            # Default fallbacks or direct char
            return keyboard.KeyCode.from_char(key_str)
        except Exception:
            return None

    def init(self):
        # Startup: Only attempt Spotify auth if enabled
        if not self.spotify_enabled or not self.spotify_api:
            return
            
        # Run in thread to not block startup logic
        def startup_auth():
             self.spotify_api.fetch_token(prompt_user=True)
             
        Thread(target=startup_auth, daemon=True).start()

    def run(self):
        while True:
            if not self.enabled:
                sleep(1 / self.fps)
                if self.state != -1: # Reset state visualization if disabled
                   pass
                continue

            # Check if SteelSeries GG is running
            gg_running = is_process_running(["SteelSeriesGG.exe", "SteelSeriesGGClient.exe", "SteelSeriesEngine3.exe"])
            
            if not gg_running:
                 self._gg_was_running = False
                 logger.debug(f"GG not running. auto_launch_gg={self.auto_launch_gg}")
                 
                 # Auto-launch logic
                 if self.auto_launch_gg:
                     now_sec = time()
                     time_since_last = now_sec - self._last_launch_attempt
                     logger.debug(f"Time since last attempt: {time_since_last:.1f}s")
                     if time_since_last > 60: # Limit attempts to once per minute
                         self._last_launch_attempt = now_sec
                         gg_path = find_steelseries_gg_path()
                         logger.info(f"Found GG path: {gg_path}")
                         if gg_path:
                             logger.info("SteelSeries GG not found. Auto-launching...")
                             # Launch with same args as official shortcut
                             args = r'-dataPath="C:\ProgramData\SteelSeries\GG" -dbEnv=production'
                             result = launch_process(gg_path, args, minimized=True)
                             logger.info(f"Launch result: {result}")
                             sleep(15) # Wait for it to start
                         else:
                             logger.warning("Auto-launch enabled but SteelSeries GG path not found.")

                 sleep(2) 
                 continue
            
            # If it was NOT running and NOW it is, trigger a reset
            if not self._gg_was_running:
                logger.info("SteelSeries GG detected! Reconnecting...")
                self.steelseries_api.reset()
                self._gg_was_running = True

            now_ms = int(time() * 1000)

            # 0) RGB Update (External lighting)
            if self.user_preferences.get_preference("rgb_enabled"):
                if now_ms - self._last_rgb_send_ms >= 1000:
                    self._last_rgb_send_ms = now_ms
                    color = self.user_preferences.get_preference("rgb_color")
                    if color and len(color) == 3:
                        self.steelseries_api.send_rgb(color[0], color[1], color[2])

            # 1) YT poll (hızlı)
            self.volume_overlay.update()

            # Media poll - Extension (Priority) then SMTC
            if now_ms - self._last_yt_poll_ms >= self._yt_poll_ms:
                self._last_yt_poll_ms = now_ms
                
            # Fetch both sources
            ext_data = self.extension_receiver.get_latest_data()
            
            with self._smtc_lock:
                smtc_fb = self._smtc_data.copy() if self._smtc_data else {}
            
            smtc_active = bool(smtc_fb and (smtc_fb.get("title") or smtc_fb.get("artist")))
            ext_active = ext_data is not None
            
            payload = None

            if smtc_active and ext_active:
                # MERGE: Extension has best Title/Artist, SMTC has best Duration/Progress
                self._extension_last_data_ms = now_ms
                is_playing = bool(ext_data.get("playing"))
                
                prog = int(ext_data.get("progress") * 1000)
                dur = int(ext_data.get("duration") * 1000)
                
                # If SMTC is reporting a valid duration, let it override the extension
                if smtc_fb.get("duration", -1) > 0:
                    prog = smtc_fb.get("progress", prog)
                    dur = smtc_fb.get("duration", dur)
                    is_playing = not bool(smtc_fb.get("paused", not is_playing))
                
                payload = {
                    "title": ext_data.get("title") or smtc_fb.get("title"),
                    "artist": ext_data.get("artist") or smtc_fb.get("artist"),
                    "progress": prog,
                    "duration": dur,
                    "paused": not is_playing,
                    "source": "youtube"
                }

            elif ext_active:
                # ONLY EXTENSION
                self._extension_last_data_ms = now_ms
                is_playing = bool(ext_data.get("playing"))
                payload = {
                    "title": ext_data.get("title"),
                    "artist": ext_data.get("artist"),
                    "progress": int(ext_data.get("progress") * 1000),
                    "duration": int(ext_data.get("duration") * 1000),
                    "paused": not is_playing,
                    "source": "youtube"
                }

            elif smtc_active:
                # Stickiness for extension: if closed recently, don't glitch to basic SMTC names
                in_ext_lock = (now_ms - self._extension_last_data_ms) < (self._extension_lock_seconds * 1000)
                if not in_ext_lock:
                    # ONLY SMTC
                    src_app = (smtc_fb.get("source") or "").lower()
                    source = "youtube" if any(x in src_app for x in ["chrome", "edge", "firefox", "opera"]) else "generic"
                    if "spotify" in src_app: source = "spotify"
                    
                    payload = smtc_fb.copy()
                    payload["source"] = source

            if payload:
                self._yt_last_seen_ms = now_ms
                self._yt_paused = bool(payload.get("paused", False))
                if not self._yt_paused:
                    self._yt_last_playing_ms = now_ms
                
                # Spotify priority check (Spotify wins if officially playing)
                spotify_active = (not self._spotify_paused) and \
                                 ((now_ms - self._spotify_last_playing_ms) <= self._spotify_hold_playing_ms)
                
                if not spotify_active:
                    self._apply_to_player(self.player, payload, now_ms, source=payload.get("source", "youtube"))

            # 2) Spotify poll (normal) - only if Spotify is enabled
            if self.spotify_api and now_ms - self._last_spotify_poll_ms >= self._spotify_poll_ms:
                self._last_spotify_poll_ms = now_ms
                # Submit to persistent worker thread instead of creating new threads
                try:
                    self._spotify_queue.put_nowait(self.spotify_api)
                except Exception:
                    pass  # Queue full = previous poll still running, skip

            # 3) Hangi kaynağı göstereceğiz?
            # FIX: Pause olduğu an (not paused) False döner ve direkt saate düşer.
            # Hold süresine sadece "playing" sinyali geliyorken bakılır.
            
            is_spotify_running = (not self._spotify_paused)
            spotify_playing_active = is_spotify_running and \
                                     ((now_ms - self._spotify_last_playing_ms) <= self._spotify_hold_playing_ms)

            is_yt_running = (not self._yt_paused)
            yt_playing_active = is_yt_running and \
                                ((now_ms - self._yt_last_playing_ms) <= self._yt_hold_playing_ms)

            if spotify_playing_active:
                self.state = State.SHOW_PLAYER
            elif yt_playing_active:
                self.state = State.SHOW_PLAYER
            else:
                self.state = State.SHOW_CLOCK

            frame_data = None

            # Calculator overlay takes priority over everything when active
            if self._calculator_active:
                img = self.calculator.get_image()
                frame_data = convert_to_bitmap(img.getdata())
            # Hardware monitor overlay > volume overlay > everything
            elif self.display_hw_monitor or self.hardware_monitor.should_display():
                img = self.hardware_monitor.get_image()
                frame_data = convert_to_bitmap(img.getdata())
            # volume overlay > everything else
            elif self.volume_overlay.should_display():
                img = self.volume_overlay.get_image()
                frame_data = convert_to_bitmap(img.getdata())
            else:
                if self.state == State.SHOW_CLOCK and self.display_clock:
                    img = self.timer.get_image()
                    frame_data = convert_to_bitmap(img.getdata())
                elif self.state == State.SHOW_PLAYER and self.display_player:
                    img = self.player.next_step()
                    frame_data = convert_to_bitmap(img.getdata())

                    # paused threshold (Yedek kontrol, yukarıdaki mantık bunu zaten çözüyor ama kalsın)
                    if self.player.pause_started and (int(time() * 1000) - self.player.pause_started) > self.timer_threshold:
                        self.state = State.SHOW_CLOCK

            # Send if image changed OR every 1 second anyway (to "claim" OLED back from games)
            now_sec = time()
            if frame_data is not None:
                if (frame_data != self._last_sent_frame) or (now_sec - self._last_frame_sent_time > 1.0):
                    try:
                        self.steelseries_api.send_frame(frame_data)
                        self._last_sent_frame = frame_data
                        self._last_frame_sent_time = now_sec
                    except Exception:
                        pass

            # Heartbeat: keep the game registered with SteelSeries GG (every 30s)
            if now_sec - self._last_heartbeat_time > 30.0:
                self._last_heartbeat_time = now_sec
                try:
                    self.steelseries_api.heartbeat()
                except Exception:
                    pass

            sleep(1 / self.fps)

    def _spotify_worker_loop(self):
        """Persistent worker thread for Spotify polling (prevents thread leak)."""
        while True:
            try:
                spotify_api = self._spotify_queue.get(timeout=2.0)
                self._poll_spotify(spotify_api)
            except Empty:
                continue  # No work, loop back
            except Exception:
                pass

    def _poll_spotify(self, spotify_api):
        try:
            song_data = spotify_api.fetch_song()
            if not song_data:
                return

            now_ms = int(time() * 1000)

            self._spotify_last_seen_ms = now_ms
            self._spotify_paused = bool(song_data.get("paused", False))
            if not self._spotify_paused:
                self._spotify_last_playing_ms = now_ms

            # Spotify paused ise ve YT aktif çalıyorsa overwrite etme
            yt_active = (not self._yt_paused) and \
                        ((now_ms - self._yt_last_playing_ms) <= self._yt_hold_playing_ms)
            
            if yt_active and self._spotify_paused:
                return

            payload = {
                "title": song_data.get("title", ""),
                "artist": song_data.get("artist", ""),
                "progress": int(song_data.get("progress") or 0),
                "duration": max(int(song_data.get("duration") or 1), 1),
                "paused": self._spotify_paused,
            }
            self._apply_to_player(self.player, payload, now_ms, source="spotify")
        except Exception:
            pass

    @staticmethod
    def _apply_to_player(player, data, now_ms: int, source="spotify"):
        """
        Scroll resetlenmesin diye:
        - title/artist değiştiyse update_song
        - aynıysa sadece seek_song (progress güncelle)
        """
        try:
            title = (data.get("title") or "").strip()
            artist = (data.get("artist") or "").strip()
            raw_progress = data.get("progress")
            raw_duration = data.get("duration")
            paused = bool(data.get("paused", False))

            # Check if song changed FIRST (before resolving duration)
            changed = True
            try:
                cur_title = player.title.content
                cur_artist = player.artist.content
                changed = (cur_title != title) or (cur_artist != artist)
            except Exception:
                changed = True

            # If SMTC returned -1 (unknown timeline) AND same song: keep cached values
            # If song changed with no timeline: update title/artist only, don't reset time
            if raw_duration is not None and int(raw_duration) == -1:
                if not changed:
                    # Same song — keep the player's existing cached data
                    duration = max(player.song_duration, 1)
                    progress = player.song_position if (raw_progress is None or int(raw_progress) == -1) else max(int(raw_progress), 0)
                else:
                    # New song but no timeline data from SMTC
                    # Update title/artist/source immediately, but DON'T reset duration
                    # to avoid 00:00/00:00 flash. Duration will come from Spotify API shortly.
                    player.title.set_text(title)
                    player.artist.set_text(artist)
                    player.source = source
                    player.song_position = 0
                    player.changed = True
                    player.step = 0
                    player.title.set_step(0)
                    player.artist.set_step(0)
                    # Skip the rest — don't call update_song with bad duration
                    if not player.paused and paused:
                        player.pause_started = now_ms
                    elif player.paused and not paused:
                        player.pause_started = 0
                    player.set_paused(paused)
                    return
            else:
                progress = int(raw_progress or 0)
                duration = int(raw_duration or 1)

            if duration <= 0:
                duration = 1
                progress = 0
            if progress < 0:
                progress = 0

            if changed:
                player.update_song(title, artist, progress, duration, paused, source)
            else:
                # Same song: update duration if a better value arrived
                # (e.g. SMTC set it to 1 initially, then Spotify API sent the real value)
                if duration > 1 and duration != player.song_duration:
                    player.song_duration = duration
                    player.changed = True

                # Update progress position (jitter-free sync)
                if not paused:
                    # --- JITTER-FREE SYNC BAŞLANGIÇ ---
                    current_pos = player.song_position
                    diff = progress - current_pos  # Gecikme farkı
                    
                    # Eğer kullanıcı videoyu ileri/geri sarmışsa (2sn üstü fark) zorla güncelle
                    if abs(diff) > 2000:
                         player.seek_song(progress)
                    
                    # Eğer duraklatılmışsa (PAUSE), tam yerini göster (flicker burada önemli değil)
                    elif paused and abs(diff) > 200:
                         player.seek_song(progress)
                    
                    # Eğer çalıyorsa ve fark çok büyük değilse:
                    # Geriye doğru gidişi engelle (Jitter'ın ana sebebi odur).
                    # Sadece ciddi bir gerileme/fark varsa müdahale et.
                    elif not paused:
                        # Eğer gelen veri mevcut konumumuzdan ÖNDEYSE ve fark 500ms+ ise snap yap
                        if diff > 500:
                            player.seek_song(progress)
                        # Eğer gelen veri ARKADAYSA ama fark küçükse güncelleme YAPMA (flicker önle)
                    # --- JITTER-FREE SYNC BİTİŞ ---

            # pause bookkeeping
            if not player.paused and paused:
                player.pause_started = now_ms
            elif player.paused and not paused:
                player.pause_started = 0

            player.set_paused(paused)
        except Exception:
            pass

    def update_config(self):
        if not self.user_preferences.load_preferences():
            logger.error("Failed to update configuration")
            return

        self.update_preferences()
        logger.info("Configuration updated successfully")

    def _poll_smtc_loop(self):
        """Background thread that polls SMTC every 200ms using a persistent event loop."""
        import ctypes
        try:
            ctypes.windll.ole32.CoInitialize(0)
        except Exception as e:
            logger.warning(f"CoInitialize failed: {e}")

        logger.info("SMTC poll loop started")

        async def runner():
            while True:
                try:
                    data = await self.windows_media.get_media_info()
                    with self._smtc_lock:
                        self._smtc_data = data
                    
                    # Log occasionally if media found
                    # if data and data.get("title"):
                    #    logger.info(f"SMTC: {data.get('source')} -> {data.get('title')[:30]}")
                    
                except (OSError, RuntimeError) as e:
                    # COM threading error - reset manager
                    logger.debug(f"SMTC COM error, resetting: {e}")
                    self.windows_media.manager = None
                except Exception as e:
                    logger.debug(f"SMTC poll error: {e}")
                
                await asyncio.sleep(0.2)

        # Keep restarting the loop if it crashes (SMTC/WinRT can be unstable)
        while True:
            try:
                # Use persistent event loop instead of asyncio.run() to avoid thread issues
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(runner())
                finally:
                    loop.close()
            except (OSError, RuntimeError) as e:
                # COM/threading error - common with WinRT
                logger.debug(f"SMTC loop COM error, restarting: {e}")
            except Exception as e:
                logger.error(f"SMTC loop crashed, restarting in 2s: {e}")
            
            import time as _time
            _time.sleep(2)
            # Reset manager to force re-init
            self.windows_media.manager = None
            # Re-initialize COM for this thread
            try:
                ctypes.windll.ole32.CoUninitialize()
                ctypes.windll.ole32.CoInitialize(0)
            except Exception:
                pass
