import logging
import pythoncom
import os
import gc
from time import time

from PIL import Image, ImageDraw
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IMMDeviceEnumerator, EDataFlow, ERole
from comtypes import CLSCTX_ALL
from ctypes import POINTER, cast

from src.image_utils import fetch_content_path

logger = logging.getLogger("OLED Customizer.VolumeOverlay")

class VolumeOverlay:
    def __init__(self, config, timeout=1.5):
        self.config = config
        self.timeout = timeout
        self.app_start_time = time() # Guard against startup flicker

        self._last_vol = None
        self._last_mute = None
        self._last_mic_mute = None
        self._last_change = 0.0

        # Audio Interfaces
        self._volume = None
        self._mic_volume = None
        
        # Init Speakers
        try:
            device = AudioUtilities.GetSpeakers()
            self._volume = device.EndpointVolume.QueryInterface(IAudioEndpointVolume)
        except Exception as e:
            logger.warning("Speaker init failed: %s", e)

        # Init Mic
        self._init_microphone()

        # Load Icons (V4)
        self.icons = {}
        self._load_icons()
        
        # Discord State
        self._discord_running = False
        self._discord_connected = False # Set by DisplayManager
        self._last_discord_check = 0
        self._mic_changed_externally = False
        self._last_synced_mic_mute = None
        
        # Discord RPC mute state (set externally by DisplayManager's Discord RPC thread)
        self._discord_muted = None   # None = unknown/not connected, True/False = mute state
        self._discord_deafened = None
        self._discord_connected = False  # True when IPC pipe is connected
        
        # Initial state fetch to prevent showing overlay on startup
        self._silent_init()

    def _init_microphone(self):
        """Initialize the default communications microphone via pycaw."""
        self._mic_volume = None
        try:
            from pycaw.pycaw import AudioUtilities as AU
            devices = AU.GetMicrophone()
            if devices:
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._mic_volume = cast(interface, POINTER(IAudioEndpointVolume))
            else:
                logger.warning("No microphone found")
        except Exception as e:
            logger.warning(f"Microphone init failed: {e}")
        finally:
            # Note: self._mic_volume holds the persistent reference if success.
            # We don't want to CoUninitialize here if it might break the persistent comtypes objects.
            pass

    def _silent_init(self):
        """Fetch initial state without triggering the overlay."""
        try:
            if self._volume:
                self._last_vol = int(round(self._volume.GetMasterVolumeLevelScalar() * 100))
                self._last_mute = bool(self._volume.GetMute())
            if self._mic_volume:
                self._last_mic_mute = bool(self._mic_volume.GetMute())
        except Exception as e:
            logger.debug(f"Silent init failed: {e}")
        self._last_change = 0.0

    def _load_icons(self):
        # V4 Clean Icons
        mapping = {
            "speaker_mute": "speaker_mute.png",
            "speaker_low": "speaker_low.png",
            "speaker_mid": "speaker_mid.png",
            "speaker_high": "speaker_high.png",
            "mic_on": "mic_on.png",
            "mic_off": "mic_off.png"
        }
        
        for key, filename in mapping.items():
            try:
                path = fetch_content_path(f"assets/icons/{filename}")
                if os.path.exists(path):
                    self.icons[key] = Image.open(path).convert("1")
            except Exception:
                pass
                
    def _set_mic_mute_on_device(self, device, new_state):
        """Helper to set mute on a single device, returns success"""
        interface = None
        volume = None
        try:
            from pycaw.pycaw import IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(new_state, None)
            return True
        except Exception:
            return False
        finally:
            # Drop COM refs immediately so caller can CoUninitialize safely.
            volume = None
            interface = None

    def _sync_all_capture_mics(self, muted, source="Sync"):
        """Set mute on all active capture devices. Returns True if at least one device was updated."""
        success_count = 0
        total_count = 0
        # COM is now initialized at the thread level in DisplayManager._discord_rpc_loop,
        # so we don't need to open/close it here (which causes comtypes VTable errors).
        try:
            import comtypes
            from comtypes import CLSCTX_ALL, GUID
            from pycaw.pycaw import IMMDeviceEnumerator, EDataFlow

            clsid = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
            enumerator = comtypes.CoCreateInstance(
                clsid, interface=IMMDeviceEnumerator, clsctx=CLSCTX_ALL
            )
            # DEVICE_STATE_ACTIVE = 0x1
            collection = enumerator.EnumAudioEndpoints(EDataFlow.eCapture.value, 0x1)

            total_count = collection.GetCount()
            for i in range(total_count):
                dev = collection.Item(i)
                if self._set_mic_mute_on_device(dev, muted):
                    success_count += 1
                dev = None
        except Exception as e:
            logger.debug("%s all-capture sync failed: %s", source, e)
        finally:
            # Release COM wrappers. comtypes will clean these up when the thread/apartment eventually closes.
            dev = None
            collection = None
            enumerator = None
            try:
                gc.collect()
            except Exception:
                pass

        if success_count > 0:
            self._last_mic_mute = muted
            logger.info(
                "%s: Synced system mics muted=%s (%s/%s devices)",
                source,
                muted,
                success_count,
                total_count,
            )
            return True

        return False

    def set_discord_mute(self, muted, deafened, connected):
        """Called by DisplayManager when Discord RPC reports a mute/deaf state change.
        
        Args:
            muted: True if mic is muted in Discord, False if unmuted, None if unknown
            deafened: True if deafened in Discord, False if not, None if unknown  
            connected: True if Discord IPC pipe is connected
        """
        old_muted = self._discord_muted
        old_deafened = self._discord_deafened
        old_connected = self._discord_connected
        
        self._discord_muted = muted
        self._discord_deafened = deafened
        self._discord_connected = connected
        
        # Combined mute state: either muted or deafened
        effective_mute = bool(muted or deafened)
        
        # Trigger overlay/sync if either state changed
        state_changed = (connected and (muted != old_muted or deafened != old_deafened))
        # We always attempt to sync the Discord state to the physical Windows device
        # so that the actual audio stream is gated even if the headset LED is already red.
        if state_changed:
            self._last_mic_mute = effective_mute
            synced = self._sync_all_capture_mics(effective_mute, source="Discord")

            # Fallback: try cached default mic interface if enumeration path didn't update anything.
            if not synced and self._mic_volume:
                try:
                    self._mic_volume.SetMute(effective_mute, None)
                    logger.info(
                        "Discord: Fallback sync via default mic interface muted=%s",
                        effective_mute,
                    )
                except Exception as e:
                    logger.warning("Failed to sync Discord state to System Mic: %s", e)
             
            if time() - self.app_start_time > 4.0:
                self._last_change = time()
            
            logger.info(f"Discord voice changed: muted={muted}, deaf={deafened} -> Syncing to System Mic")
        
        # If Discord just connected/disconnected, trigger overlay briefly
        if connected != old_connected:
            if time() - self.app_start_time > 4.0:
                self._last_change = time()

    def toggle_mic_mute(self):
        """Toggle mic mute state.
        
        If Discord IPC is connected, this is a no-op — Discord handles muting.
        Otherwise falls back to system mic mute (legacy behavior).
        """
        # If Discord is connected, don't touch system mics — Discord handles it
        if self._discord_connected:
            logger.info("Discord connected — mic mute is handled by Discord, skipping system toggle")
            return
        
        # --- LEGACY FALLBACK: System mic mute when Discord is NOT running ---
        coinit_done = False
        default_mic = None
        interface = None
        mic_volume = None
        enumerator = None
        collection = None
        dev = None
        try:
            pythoncom.CoInitialize()
            coinit_done = True
        except Exception:
            pass

        try:
            from pycaw.pycaw import AudioUtilities as AU
            from pycaw.pycaw import IAudioEndpointVolume
            from comtypes import CLSCTX_ALL, GUID
            
            try:
                # --- PHASE 1: Try Standard Roles ---
                target_roles = [ERole.eCommunications.value, ERole.eMultimedia.value]
                default_mic = None
                
                for role in target_roles:
                    try:
                        default_mic = AU.GetMicrophone(role)
                        if default_mic:
                            break
                    except Exception:
                        continue

                if default_mic:
                    try:
                        interface = default_mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                        mic_volume = cast(interface, POINTER(IAudioEndpointVolume))
                        new_state = not bool(mic_volume.GetMute())
                        mic_volume.SetMute(new_state, None)
                        self._last_mic_mute = new_state
                        if time() - self.app_start_time > 4.0: self._last_change = time()
                        logger.info(f"Toggled Default Mic Mute to {new_state}")
                        return
                    except Exception:
                        pass

                # --- PHASE 2: NUCLEAR OPTION ---
                try:
                    from pycaw.pycaw import IMMDeviceEnumerator, EDataFlow
                    import comtypes
                    clsid = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
                    enumerator = comtypes.CoCreateInstance(clsid, interface=IMMDeviceEnumerator, clsctx=CLSCTX_ALL)
                    collection = enumerator.EnumAudioEndpoints(EDataFlow.eCapture.value, 0x1) 
                    
                    count = collection.GetCount()
                    if count > 0:
                        target_mute_state = not (self._last_mic_mute if self._last_mic_mute is not None else False)
                        success_count = 0
                        for i in range(count):
                            dev = collection.Item(i)
                            if self._set_mic_mute_on_device(dev, target_mute_state):
                                success_count += 1
                            dev = None
                        
                        if success_count > 0:
                            self._last_mic_mute = target_mute_state
                            if time() - self.app_start_time > 4.0: self._last_change = time()
                            logger.info(f"Nuclear Mute success: Toggled {success_count}/{count} devices to {target_mute_state}")
                            return
                except Exception as e:
                    logger.debug(f"Nuclear search failed: {e}")

                logger.warning("No microphone device found during toggle")
            except Exception as e:
                logger.warning(f"System mic control failed: {e}")
        finally:
            # Release COM wrappers before uninitializing apartment.
            dev = None
            collection = None
            enumerator = None
            mic_volume = None
            interface = None
            default_mic = None
            # Flush cyclic COM wrappers before CoUninitialize.
            try:
                gc.collect()
            except Exception:
                pass
            # CRITICAL: Always uninitialize COM to prevent handle leaks over long runtimes
            if coinit_done:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        # Fallback: Overlay Only
        if self._last_mic_mute is None: self._last_mic_mute = False
        self._last_mic_mute = not self._last_mic_mute
        if time() - self.app_start_time > 4.0: self._last_change = time()
        logger.info(f"Fallback mode (Visual Only): Mic mute overlay = {self._last_mic_mute}")

    def set_mic_mute_from_hardware(self, muted):
        """Called by HIDListener to sync physical headset state to App/Discord."""
        if muted != self._last_mic_mute:
            self._last_mic_mute = muted
            self._mic_changed_externally = True 
            if time() - self.app_start_time > 4.0:
                self._last_change = time()
            logger.info(f"Hardware Mic change propagated: muted={muted}")

            # Snappy UI: If Discord is connected, update the displayed mute state immediately
            # so the OLED doesn't lag behind the physical button press.
            if self._discord_connected:
                self._discord_muted = muted

            # Keep all active system capture devices aligned with headset hardware state.
            if not self._sync_all_capture_mics(muted, source="Hardware"):
                logger.debug("Hardware-to-System sync failed: no active capture device was updated")

    def _check_discord(self):
        """Lighter check for Discord presence based on existing RPC connection status.
        This avoids expensive process iteration (psutil).
        """
        if time() - self._last_discord_check < 2.0:
            return
        
        self._last_discord_check = time()
        
        # We rely on DisplayManager setting _discord_connected via RPC
        running = self._discord_connected
        
        if running != self._discord_running:
            self._discord_running = running
            # Check for actual change before triggering overlay
            if time() - self.app_start_time > 4.0:
                self._last_change = time()

    def update(self):
        self._check_discord()
        changed = False
        
        # Check Speaker
        if self._volume:
            try:
                # GetMasterVolumeLevelScalar can throw if audio device is lost
                vol = int(round(self._volume.GetMasterVolumeLevelScalar() * 100))
                mute = bool(self._volume.GetMute())
                
                if self._last_vol is None:
                    # Initial state capture - do not trigger overlay
                    self._last_vol = vol
                    self._last_mute = mute
                elif vol != self._last_vol or mute != self._last_mute:
                    self._last_vol = vol
                    self._last_mute = mute
                    changed = True
            except Exception as e:
                logger.debug(f"Speaker update failed: {e}")
                # Try to re-init speaker (device may have changed)
                try:
                    device = AudioUtilities.GetSpeakers()
                    self._volume = device.EndpointVolume.QueryInterface(IAudioEndpointVolume)
                    logger.warning("Re-initialized speaker interface after failure")
                except Exception:
                    self._volume = None
                
        # Check Mic
        if self._mic_volume:
            try:
                mic_mute = bool(self._mic_volume.GetMute())
                if self._last_mic_mute is None:
                    # Initial state capture - do not trigger overlay
                    self._last_mic_mute = mic_mute
                elif mic_mute != self._last_mic_mute:
                    self._last_mic_mute = mic_mute
                    changed = True
            except Exception as e:
                logger.debug(f"Mic update failed: {e}")
                # Try to re-init mic (device may have changed)
                self._init_microphone()
                if self._mic_volume:
                    logger.warning("Re-initialized microphone interface after failure")
        
        if changed:
            # Shield against startup flicker - wait 4 seconds before allowing overlay to show
            if time() - self.app_start_time > 4.0:
                self._last_change = time()

    def should_display(self) -> bool:
        if self._last_change == 0.0:
            return False
        return (time() - self._last_change) < self.timeout

    def get_image(self):
        w, h = self.config.width, self.config.height
        image = Image.new("1", (w, h), color=self.config.secondary)
        draw = ImageDraw.Draw(image)

        # 1. Speaker Icon
        icon_key = "speaker_mute"
        if not self._last_mute:
            if self._last_vol == 0: icon_key = "speaker_mute"
            elif self._last_vol < 33: icon_key = "speaker_low"
            elif self._last_vol < 66: icon_key = "speaker_mid"
            else: icon_key = "speaker_high"
        else:
             icon_key = "speaker_mute"
            
        if icon_key in self.icons:
            image.paste(self.icons[icon_key], (2, 14))
            
        # 2. Mic Icon — Discord state takes priority, falls back to system mic state
        mic_width = 0
        mic_mute_state = self._last_mic_mute  # System mic state (fallback)
        if self._discord_connected and (self._discord_muted is not None or self._discord_deafened is not None):
            # Combined mute state for display: either muted OR deafened
            mic_mute_state = bool(self._discord_muted or self._discord_deafened)
        
        if mic_mute_state is not None:
            mic_width = 12
            mic_key = "mic_off" if mic_mute_state else "mic_on"
            if mic_key in self.icons:
                image.paste(self.icons[mic_key], (w - 14, 14))

        bar_x1 = 18
        if self._last_mic_mute is not None:
             bar_x2 = w - 18
        else:
             bar_x2 = w - 4 
             
        bar_y1 = 16
        bar_y2 = h - 16
        
        draw.rectangle((bar_x1, bar_y1, bar_x2, bar_y2), outline=self.config.primary)
        
        if not self._last_mute and self._last_vol and self._last_vol > 0:
            fill_width = int((bar_x2 - bar_x1 - 2) * (self._last_vol / 100))
            if fill_width > 0:
                draw.rectangle(
                    (bar_x1 + 2, bar_y1 + 2, bar_x1 + 2 + fill_width, bar_y2 - 2),
                    fill=self.config.primary
                )

        return image
