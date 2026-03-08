import logging
import os
from time import time
import psutil

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

        # Init Mic (Communication Default) - using pycaw
        try:
            # Get the default communications microphone
            from pycaw.pycaw import AudioUtilities as AU
            devices = AU.GetMicrophone()
            if devices:
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._mic_volume = cast(interface, POINTER(IAudioEndpointVolume))
            else:
                logger.warning("No microphone found")
        except Exception as e:
            logger.warning(f"Microphone init failed: {e}")
            try:
                # Fallback
                device = AudioUtilities.GetMicrophone()
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._mic_volume = interface.QueryInterface(IAudioEndpointVolume)
            except:
                pass

        # Load Icons (V4)
        self.icons = {}
        self._load_icons()
        
        # Discord State
        self._discord_running = False
        self._last_discord_check = 0
        
        # Initial state fetch to prevent showing overlay on startup
        self._silent_init()

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
        try:
            from pycaw.pycaw import IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(new_state, None)
            return True
        except:
            return False

    def toggle_mic_mute(self):
        """Toggle mic mute state - Nuclear Option: Mutes ALL active capture devices if no default found."""
        import ctypes
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except:
            pass

        try:
            from pycaw.pycaw import AudioUtilities as AU
            from pycaw.pycaw import IAudioEndpointVolume
            from comtypes import CLSCTX_ALL, GUID
            
            # --- PHASE 1: Try Standard Roles (Headsets/Comms) ---
            target_roles = [ERole.eCommunications.value, ERole.eMultimedia.value]
            default_mic = None
            
            for role in target_roles:
                try:
                    default_mic = AU.GetMicrophone(role)
                    if default_mic:
                        break
                except:
                    continue

            # If we found a default, just toggle that lone one
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
                except:
                    pass

            # --- PHASE 2: NUCLEAR OPTION (Search for ALL capture devices) ---
            # If default wasn't found or activation failed, mute EVERYTHING ACTIVE.
            try:
                from pycaw.pycaw import IMMDeviceEnumerator, EDataFlow
                import comtypes
                clsid = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
                enumerator = comtypes.CoCreateInstance(clsid, interface=IMMDeviceEnumerator, clsctx=CLSCTX_ALL)
                collection = enumerator.EnumAudioEndpoints(EDataFlow.eCapture.value, 0x1) # DEVICE_STATE_ACTIVE
                
                count = collection.GetCount()
                if count > 0:
                    # Use a stable toggle target based on our internal state if possible
                    target_mute_state = not (self._last_mic_mute if self._last_mic_mute is not None else False)
                    success_count = 0
                    
                    for i in range(count):
                        dev = collection.Item(i)
                        if self._set_mic_mute_on_device(dev, target_mute_state):
                            success_count += 1
                            logger.debug(f"Nuclear Mute: Toggled device {dev.GetId()}")
                    
                    if success_count > 0:
                        self._last_mic_mute = target_mute_state
                        if time() - self.app_start_time > 4.0: self._last_change = time()
                        logger.info(f"Nuclear Mute success: Toggled {success_count}/{count} devices to {target_mute_state}")
                        return
            except Exception as e:
                logger.debug(f"Nuclear search failed: {e}")

            logger.warning("No microphone device found in any role or deep search during toggle")
        except Exception as e:
            logger.warning(f"System mic control failed: {e}")

        # Fallback: Overlay Only
        if self._last_mic_mute is None: self._last_mic_mute = False
        self._last_mic_mute = not self._last_mic_mute
        if time() - self.app_start_time > 4.0: self._last_change = time()
        logger.info(f"Fallback mode (Visual Only): Mic mute overlay = {self._last_mic_mute}")

    def _check_discord(self):
        if time() - self._last_discord_check < 2.0:
            return
        
        self._last_discord_check = time()
        running = False
        try:
             for p in psutil.process_iter(['name']):
                 if p.info['name'] and 'discord' in p.info['name'].lower():
                     running = True
                     break
        except:
            pass
        
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
                except:
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
                try:
                    from pycaw.pycaw import AudioUtilities as AU
                    devices = AU.GetMicrophone()
                    if devices:
                        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                        self._mic_volume = cast(interface, POINTER(IAudioEndpointVolume))
                        logger.warning("Re-initialized microphone interface after failure")
                except:
                    self._mic_volume = None
        
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
            
        # 2. Mic Icon (Always show if state is known)
        mic_width = 0
        if self._last_mic_mute is not None:
            mic_width = 12
            mic_key = "mic_off" if self._last_mic_mute else "mic_on"
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