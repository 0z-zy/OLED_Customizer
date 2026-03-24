import logging
import threading
import ctypes
from ctypes import wintypes
from time import sleep

logger = logging.getLogger("OLED Customizer.HIDListener")

# Define Win32 API signatures for 64-bit compatibility
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

CreateFileA = kernel32.CreateFileA
CreateFileA.restype = wintypes.HANDLE
CreateFileA.argtypes = [
    wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
]

ReadFile = kernel32.ReadFile
ReadFile.restype = wintypes.BOOL
ReadFile.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID
]

WriteFile = kernel32.WriteFile
WriteFile.restype = wintypes.BOOL
WriteFile.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID
]

CloseHandle = kernel32.CloseHandle
CloseHandle.restype = wintypes.BOOL
CloseHandle.argtypes = [wintypes.HANDLE]

HID_GUID = "{4d1e55b2-f16f-11cf-88cb-001111000030}"

class HIDListener(threading.Thread):
    def __init__(self, volume_overlay):
        super().__init__(daemon=True, name="HIDListener")
        self.volume_overlay = volume_overlay
        self.device_read_path = None
        self.device_write_path = None
        self._running = False
        self._last_state = None
        self._lock = threading.Lock()
        self._handle = None

    def find_device_paths(self):
        import winreg
        read_path = None
        write_path = None
        
        try:
            class_path = f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{HID_GUID}"
            h_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            
            for i in range(100):
                try:
                    device_instance_key = winreg.EnumKey(h_key, i)
                    if "VID_03F0&PID_06BE" in device_instance_key.upper():
                        # We must open the device key to find the actual # symlink
                        dev_h = winreg.OpenKey(h_key, device_instance_key)
                        for j in range(20):
                            try:
                                ref_name = winreg.EnumKey(dev_h, j)
                                # Build full path: \\?\HID...#{GUID}\#Reference
                                base_path = device_instance_key.replace("##?#", "\\\\?\\")
                                full_path = f"{base_path}\\{ref_name}"
                                
                                # CLOUD III WIRELESS: 
                                # Col05 handles BOTH read (buttons) and write (LED/Mute).
                                if "COL05" in ref_name.upper():
                                    read_path = full_path
                                    write_path = full_path
                            except OSError: break
                        winreg.CloseKey(dev_h)
                except OSError: break
            winreg.CloseKey(h_key)
        except Exception as e:
            logger.debug(f"HID Registry scan failed: {e}")
            
        return read_path, write_path

    def start(self):
        if self._running: return
        self._running = True
        
        self.device_read_path, self.device_write_path = self.find_device_paths()
        if self.device_read_path:
            logger.debug(f"HID Discovery: Input Path (Col05): {self.device_read_path}")
        if self.device_write_path:
            logger.debug(f"HID Discovery: Output Path (Col03): {self.device_write_path}")

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._running = False
        if self._handle and self._handle != wintypes.HANDLE(-1).value:
             CloseHandle(self._handle)
             self._handle = None

    def set_hardware_mute(self, is_muted):
        t = threading.Thread(target=self._do_hardware_mute, args=(is_muted,))
        t.daemon = True
        t.start()

    def _do_hardware_mute(self, is_muted):
        # Cloud III Wireless uses RID 0x0d on the SAME path as the read loop (Col05)
        if not self.device_read_path:
            logger.warning("HID Sync: Aborting, no path found.")
            return

        write_handle = CreateFileA(
            self.device_read_path.encode('ascii'),
            0x40000000, # GENERIC_WRITE
            0x01 | 0x02, # SHARE_READ | SHARE_WRITE
            None,
            3, # OPEN_EXISTING
            0,
            None
        )

        if write_handle == wintypes.HANDLE(-1).value:
            logger.warning(f"HID Sync: Cannot open write handle for Col05, err: {ctypes.get_last_error()}")
            return

        try:
            buf_len = 64
            report = bytearray(buf_len)
            # PROVEN WINNING PAYLOAD: Report ID 0x0d
            report[0] = 0x0d 
            report[1] = 0x02
            report[2] = 0x03
            report[3] = 0x00
            report[4] = 0x03
            # USER-VERIFIED PROTOCOL: 0x00 = RED (Muted), 0x01 = OFF (Unmuted)
            # Sending this with 3x Nuclear Pulse to ensure firmware capture.
            report[5] = 0x00 if is_muted else 0x01
            
            # NUCLEAR PULSE: Send the command 3 times to ensure firmware capture
            write_succeeded_at_least_once = False
            for pulse in range(3):
                bytes_written = wintypes.DWORD(0)
                success = WriteFile(write_handle, bytes(report), buf_len, ctypes.byref(bytes_written), None)
                if success:
                    logger.debug(f"Pulsed HID Write {pulse+1}/3: muted={is_muted}")
                    write_succeeded_at_least_once = True
                else:
                    logger.debug(f"HID Sync: Write failed for RID 0d on pulse {pulse+1}/3: {ctypes.get_last_error()}")
                sleep(0.05) # Tiny delay between pulses
            
            if write_succeeded_at_least_once:
                return True
            else:
                logger.warning(f"HID Sync: All 3 writes failed for RID 0d.")
                return False
        except Exception as e:
            logger.error(f"HID Sync Error: {e}")
            return False
        finally:
            CloseHandle(write_handle)

    def _listen_loop(self):
        while self._running:
            if not self.device_read_path or not self.device_write_path:
                self.device_read_path, self.device_write_path = self.find_device_paths()

            if not self.device_read_path:
                sleep(5)
                continue
                
            self._handle = CreateFileA(
                self.device_read_path.encode('ascii'),
                0x80000000, # GENERIC_READ
                0x01 | 0x02, # SHARE_READ | SHARE_WRITE
                None,
                3, # OPEN_EXISTING
                0x00000000, # synchronous
                None
            )

            if self._handle == wintypes.HANDLE(-1).value:
                self._handle = None
                sleep(2)
                continue
                
            logger.info(f"Cloud III HID Listener: Connected to {self.device_read_path}")
            
            buf_len = 64
            read_buf = ctypes.create_string_buffer(buf_len)
            bytes_read = wintypes.DWORD(0)

            while self._running and self._handle:
                try:
                    success = ReadFile(
                        self._handle,
                        read_buf,
                        buf_len,
                        ctypes.byref(bytes_read),
                        None
                    )
                    
                    if not success:
                        break
                        
                    if bytes_read.value > 0:
                        data = bytes(read_buf.raw[:bytes_read.value])
                        if len(data) >= 6 and data[0:3] == b'\x0d\x02\x03':
                            is_muted = (data[5] == 0x01)
                            if is_muted != self._last_state:
                                logger.info(f"Cloud III Raw: {data.hex()} -> Muted={is_muted}")
                                self.volume_overlay.set_mic_mute_from_hardware(is_muted)
                                self._last_state = is_muted
                except Exception as e:
                    break
            
            if self._handle and self._handle != wintypes.HANDLE(-1).value:
                CloseHandle(self._handle)
                self._handle = None
            if self._running:
                sleep(1)
