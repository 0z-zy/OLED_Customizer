from threading import Thread
from time import sleep, time
from tkinter import messagebox
import tkinter as tk
import logging

from src.SpotifyAPI import SpotifyAPI
from src.SpotifyPlayer import SpotifyPlayer
from src.SteelSeriesAPI import SteelSeriesAPI
from src.Timer import Timer
from src.volume import VolumeOverlay
from src.image_utils import convert_to_bitmap
from src.UserPreferences import UserPreferences
from src.Systray import run_systray_async
from src.WindowsMedia import WindowsMedia
from src.HardwareMonitor import HardwareMonitor
from src.ExtensionReceiver import ExtensionReceiver
from src.utils import is_process_running
import asyncio

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

logger = logging.getLogger("OLED Customizer")


class State:
    SHOW_CLOCK = 0
    SHOW_PLAYER = 1


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
        self.timer = Timer(
            config,
            self.user_preferences.get_preference("date_format"),
            self.user_preferences.get_preference("display_seconds"),
            self.user_preferences.get_preference("use_turkish_days"),
            self.user_preferences.get_preference("clock_style"),
        )

        run_systray_async(self)

        self.player = SpotifyPlayer(config, self.user_preferences, fps)
        self.spotify_api = SpotifyAPI(self.user_preferences)
        self.steelseries_api = SteelSeriesAPI()

        self.volume_overlay = VolumeOverlay(config)
        self.hardware_monitor = HardwareMonitor(config)
        self.extension_receiver = ExtensionReceiver(port=2408)
        self.extension_receiver.start()

        # Setup keyboard listener for INS key and Global Hotkeys
        if keyboard:
            self._listener = None
            self._hotkey_listener = None

        if keyboard:
            self._listener = None
            self.key_monitor_val = None
            self.key_mute_val = None
            
            def on_press(key):
                try:
                    if key == self.key_monitor_val:
                        self.hardware_monitor.trigger()
                    elif key == self.key_mute_val:
                         logger.info("Mute key pressed - Toggling Mute")
                         self.volume_overlay.toggle_mic_mute()
                except Exception as e:
                    logger.error(f"Hotkey error: {e}")
            
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            logger.info("Keyboard listener started")
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
        
        self.load_preferences()

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

        # Hotkeys
        self.key_monitor_val = self._parse_key(self.user_preferences.get_preference("hotkey_monitor"))
        self.key_mute_val = self._parse_key(self.user_preferences.get_preference("hotkey_mute"))
        logger.info(f"Hotkeys bound: Monitor={self.key_monitor_val}, Mute={self.key_mute_val}")

        self._spotify_poll_ms = max(250, int(self.fetch_delay * 1000))

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
        self.spotify_api.fetch_token()

    def run(self):
        while True:
            if not self.enabled:
                sleep(1 / self.fps)
                if self.state != -1: # Reset state visualization if disabled
                   pass
                continue

            # Check if SteelSeries GG is running
            gg_running = is_process_running(["SteelSeriesGG.exe", "SteelSeriesEngine3.exe"])
            
            if not gg_running:
                 # If not running, just sleep and wait
                 self._gg_was_running = False
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
                
                # Try Extension First
                ext_data = self.extension_receiver.get_latest_data()
                
                if ext_data:
                    # Extension is providing data (even if paused)
                    self._extension_last_data_ms = now_ms
                    is_playing = bool(ext_data.get("playing"))
                    
                    self._yt_last_seen_ms = now_ms
                    self._yt_paused = not is_playing
                    if is_playing:
                        self._yt_last_playing_ms = now_ms
                    
                    # Convert extension keys to expected player keys
                    payload = {
                        "title": ext_data.get("title"),
                        "artist": ext_data.get("artist"),
                        "progress": int(ext_data.get("progress") * 1000), # extension sends seconds
                        "duration": int(ext_data.get("duration") * 1000),
                        "paused": not is_playing,
                        "source": "youtube"
                    }
                    
                    spotify_active = (not self._spotify_paused) and \
                                     ((now_ms - self._spotify_last_playing_ms) <= self._spotify_hold_playing_ms)
                    
                    if not spotify_active:
                        self._apply_to_player(self.player, payload, now_ms, source="youtube")
                
                else:
                    # Stickiness: If we saw extension data recently, ignore SMTC fallback
                    in_extension_lock = (now_ms - self._extension_last_data_ms) < (self._extension_lock_seconds * 1000)
                    
                    if not in_extension_lock:
                        # Fallback to SMTC
                        with self._smtc_lock:
                            fb = self._smtc_data
                        
                        if fb and (fb.get("title") or fb.get("artist")):
                            self._yt_last_seen_ms = now_ms
                            self._yt_paused = bool(fb.get("paused", False))
                            if not self._yt_paused:
                                self._yt_last_playing_ms = now_ms

                            # Determine source from SMTC source app
                            src_app = (fb.get("source") or "").lower()
                            if "spotify" in src_app:
                                source = "spotify"
                            elif "chrome" in src_app or "edge" in src_app or "firefox" in src_app or "opera" in src_app:
                                source = "youtube"
                            else:
                                source = "generic"

                            # Spotify aktif çalıyorsa YT overwrite etmesin
                            spotify_active = (not self._spotify_paused) and \
                                             ((now_ms - self._spotify_last_playing_ms) <= self._spotify_hold_playing_ms)
                            
                            if not spotify_active:
                                self._apply_to_player(self.player, fb, now_ms, source=source)
                    else:
                        # No media from extension or SMTC
                        pass

            # 2) Spotify poll (normal)
            if now_ms - self._last_spotify_poll_ms >= self._spotify_poll_ms:
                self._last_spotify_poll_ms = now_ms
                Thread(
                    target=self._poll_spotify,
                    daemon=True,
                    args=(self.spotify_api,),
                ).start()

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

            # Hardware monitor overlay > volume overlay > everything
            if self.display_hw_monitor or self.hardware_monitor.should_display():
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

            # tek kanaldan gönder + duplicate skip
            if frame_data is not None and frame_data != self._last_sent_frame:
                try:
                    self.steelseries_api.send_frame(frame_data)
                    self._last_sent_frame = frame_data
                except Exception:
                    pass

            sleep(1 / self.fps)

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
            progress = int(data.get("progress") or 0)
            duration = int(data.get("duration") or 1)
            paused = bool(data.get("paused", False))

            if duration <= 0:
                duration = 1
                progress = 0
            if progress < 0:
                progress = 0

            # ✅ sadece değişince update_song (yoksa scroll her seferinde sıfırlanır)
            changed = True
            try:
                cur_title = player.title.content
                cur_artist = player.artist.content
                changed = (cur_title != title) or (cur_artist != artist)
            except Exception:
                changed = True

            if changed:
                player.update_song(title, artist, progress, duration, paused, source)
            else:
                # aynı içerik: sadece ilerleme
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
        logger.info("Configuration updated")

        def tk_popup():
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Info", "Configuration successfully updated")
            root.destroy()

        Thread(target=tk_popup, daemon=True).start()

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
                    
                except Exception as e:
                    logger.debug(f"SMTC poll error: {e}")
                
                await asyncio.sleep(0.2)

        try:
            asyncio.run(runner())
        except Exception as e:
            logger.error(f"SMTC loop crashed: {e}")
