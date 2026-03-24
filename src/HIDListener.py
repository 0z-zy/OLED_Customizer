import logging
import threading
import ctypes
from ctypes import wintypes
from time import sleep, time

logger = logging.getLogger("OLED Customizer.HIDListener")

# Define Win32 API signatures for 64-bit compatibility
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)

CreateFileW = kernel32.CreateFileW
CreateFileW.restype = wintypes.HANDLE
CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
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
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]

CloseHandle = kernel32.CloseHandle
CloseHandle.restype = wintypes.BOOL
CloseHandle.argtypes = [wintypes.HANDLE]

HidD_SetOutputReport = hid.HidD_SetOutputReport
HidD_SetOutputReport.restype = wintypes.BOOLEAN
HidD_SetOutputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]

HID_GUID = "{4d1e55b2-f16f-11cf-88cb-001111000030}"
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
SHARE_READ_WRITE = 0x01 | 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
DEVICE_MARKERS = ("VID_03F0", "VID_0951", "HYPERX", "CLOUD")

class HIDListener(threading.Thread):
    def __init__(self, volume_overlay):
        super().__init__(daemon=True, name="HIDListener")
        self.volume_overlay = volume_overlay
        self.device_path = None
        self._running = False
        self._last_state = None
        self._last_state_ts = 0.0
        self._lock = threading.Lock()
        self._handle = None
        # Col05 advertises output caps for both report IDs 0x0C and 0x0D.
        # Keep multiple profiles to support firmware variants.
        self._output_profiles = (
            (0x0D, 0x00, 0x03),  # observed input-state report shape
            (0x0C, 0x00, 0x03),  # alternate output report ID from HID caps
            (0x0D, 0x00, 0x01),  # fallback command shape variant
            (0x0C, 0x00, 0x01),  # fallback command shape variant
        )

    @staticmethod
    def _candidate_priority(path):
        upper = path.upper()
        if "COL05" in upper:
            return 0
        if "COL04" in upper:
            return 1
        if "COL06" in upper:
            return 2
        if "COL" in upper:
            return 3
        return 4

    @staticmethod
    def _build_candidate_paths(device_instance_key, ref_name=None):
        """Convert DeviceClasses key names into possible HID device paths."""
        base_path = device_instance_key.replace("##?#", "\\\\?\\")
        candidates = [base_path]

        if ref_name:
            candidates.append(f"{base_path}\\{ref_name}")

        # Some drivers expose a literal '#' child that still resolves only from base path.
        # Keep both forms to be robust across machines.
        if ref_name == "#":
            candidates.append(base_path)

        # De-duplicate while preserving order.
        unique = []
        seen = set()
        for path in candidates:
            if path and path not in seen:
                seen.add(path)
                unique.append(path)
        return unique

    @staticmethod
    def _can_open(path, access):
        """Probe whether a candidate HID path can be opened with the requested access."""
        handle = CreateFileW(
            path,
            access,
            SHARE_READ_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            return False, ctypes.get_last_error()
        CloseHandle(handle)
        return True, 0

    def find_device_path(self):
        import winreg

        logger.info("HID Discovery: Scanning registry...")

        class_path = f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{HID_GUID}"
        found_devices = []
        candidate_paths = []
        seen_candidates = set()

        try:
            h_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                class_path,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            )

            i = 0
            while True:
                try:
                    device_instance_key = winreg.EnumKey(h_key, i)
                except OSError:
                    break

                i += 1
                upper_key = device_instance_key.upper()
                if not any(marker in upper_key for marker in DEVICE_MARKERS):
                    continue

                found_devices.append(device_instance_key)
                logger.info("HID Discovery: Found device: %s", device_instance_key)

                # Newer registries already carry ColXX in the top-level key.
                for path in self._build_candidate_paths(device_instance_key):
                    if path not in seen_candidates:
                        seen_candidates.add(path)
                        candidate_paths.append(path)

                # Older layouts can still expose additional endpoint refs.
                try:
                    dev_h = winreg.OpenKey(h_key, device_instance_key)
                    j = 0
                    while True:
                        try:
                            ref_name = winreg.EnumKey(dev_h, j)
                        except OSError:
                            break

                        j += 1
                        logger.debug("HID Discovery:   Endpoint: %s", ref_name)
                        for path in self._build_candidate_paths(device_instance_key, ref_name):
                            if path not in seen_candidates:
                                seen_candidates.add(path)
                                candidate_paths.append(path)
                    winreg.CloseKey(dev_h)
                except Exception as e:
                    logger.debug("HID Discovery: Error opening device key: %s", e)

            winreg.CloseKey(h_key)

            if not found_devices:
                logger.warning("HID Discovery: No HyperX/HP devices found in registry")
                logger.info("HID Discovery: Checked path: %s", class_path)
                return None

            if not candidate_paths:
                logger.warning("HID Discovery: Found %d device(s) but no candidate paths", len(found_devices))
                return None

            best_path = None
            best_score = -1

            for candidate in sorted(candidate_paths, key=self._candidate_priority):
                read_ok, read_err = self._can_open(candidate, GENERIC_READ)
                write_ok, write_err = self._can_open(candidate, GENERIC_WRITE)

                if not read_ok and not write_ok:
                    logger.debug(
                        "HID Discovery: Candidate unusable: %s (read err=%s, write err=%s)",
                        candidate,
                        read_err,
                        write_err,
                    )
                    continue

                score = 2 if (read_ok and write_ok) else (1 if read_ok else 0)
                logger.info(
                    "HID Discovery: Candidate OK: %s (read=%s write=%s)",
                    candidate,
                    read_ok,
                    write_ok,
                )

                if score > best_score:
                    best_score = score
                    best_path = candidate

                # Col05 with read+write is the known-good path for Cloud III.
                if score == 2 and "COL05" in candidate.upper():
                    return candidate

            if best_path:
                logger.info("HID Discovery: Selected fallback path: %s", best_path)
                return best_path

            logger.warning("HID Discovery: Found %d device(s) but all candidates failed open checks", len(found_devices))
            return None

        except FileNotFoundError:
            logger.error("HID Registry path not found: %s", class_path)
            return None
        except PermissionError as e:
            logger.error("HID Registry permission error: %s", e)
            return None
        except Exception as e:
            logger.error("HID Registry scan failed: %s", e)
            return None

    def start(self):
        if self._running:
            return
        self._running = True

        self.device_path = self.find_device_path()
        if self.device_path:
            logger.info("HID Discovery: Found Cloud III at %s", self.device_path)
        else:
            logger.warning("HID Discovery: Cloud III Wireless not found")

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._running = False
        with self._lock:
            if self._handle and self._handle != INVALID_HANDLE_VALUE:
                CloseHandle(self._handle)
                self._handle = None

    def set_hardware_mute(self, is_muted):
        """Request hardware mute change."""
        t = threading.Thread(target=self._do_hardware_mute, args=(is_muted,))
        t.daemon = True
        t.start()

    def _do_hardware_mute(self, is_muted):
        """
        Write mute command to headset.
        Strategy: Use a completely separate handle for writing.
        """
        # Try to find device path if not available
        if not self.device_path:
            self.device_path = self.find_device_path()

        if not self.device_path:
            logger.warning("HID Sync: Could not find Cloud III device in registry")
            return False

        logger.debug("HID Sync: Opening write handle to %s", self.device_path)

        # Temporarily park the read handle so firmware sees a clean writer.
        # Some HID stacks accept writes only when no active blocking reader is attached.
        with self._lock:
            if self._handle and self._handle != INVALID_HANDLE_VALUE:
                try:
                    CloseHandle(self._handle)
                except Exception:
                    pass
                self._handle = None

        # Try multiple open modes from permissive to strict.
        # If the device expects exclusive control for output reports,
        # one of the strict modes should succeed.
        open_modes = (
            (GENERIC_READ | GENERIC_WRITE, SHARE_READ_WRITE, "rw-shared"),
            (GENERIC_WRITE, 0, "w-exclusive"),
            (GENERIC_READ | GENERIC_WRITE, 0, "rw-exclusive"),
        )

        write_handle = INVALID_HANDLE_VALUE
        open_mode_used = None
        for desired_access, share_mode, mode_name in open_modes:
            handle = CreateFileW(
                self.device_path,
                desired_access,
                share_mode,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if handle != INVALID_HANDLE_VALUE:
                write_handle = handle
                open_mode_used = mode_name
                break
            logger.debug(
                "HID Sync: Open mode %s failed, err=%s",
                mode_name,
                ctypes.get_last_error(),
            )

        if write_handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            logger.warning("HID Sync: Cannot open write handle in any mode, err: %s", err)
            # Force re-discovery next time if path became stale.
            self.device_path = None
            return False

        logger.debug("HID Sync: Write handle opened successfully (%s)", open_mode_used)

        try:
            logger.info("HID Sync: Sending mute=%s to headset", is_muted)

            state_byte = 0x01 if is_muted else 0x00
            write_success = 0
            output_success = 0

            for report_id, b3, b4 in self._output_profiles:
                report = bytearray(64)
                report[0] = report_id
                report[1] = 0x02
                report[2] = 0x03
                report[3] = b3
                report[4] = b4
                report[5] = state_byte

                # NUCLEAR PULSE: Send 3 times with small delays (WriteFile path)
                for pulse in range(3):
                    bytes_written = wintypes.DWORD(0)
                    result = WriteFile(write_handle, bytes(report), 64, ctypes.byref(bytes_written), None)
                    if result:
                        write_success += 1
                        logger.debug(
                            "HID Write profile RID=%02X b3=%02X b4=%02X pulse %s/3: success",
                            report_id,
                            b3,
                            b4,
                            pulse + 1,
                        )
                    else:
                        logger.debug(
                            "HID Write profile RID=%02X b3=%02X b4=%02X pulse %s/3: failed, err=%s",
                            report_id,
                            b3,
                            b4,
                            pulse + 1,
                            ctypes.get_last_error(),
                        )
                    sleep(0.02)

                # Some HID firmwares ignore WriteFile but accept HidD_SetOutputReport.
                # Try both 64-byte and 6-byte output reports.
                for out_len in (64, 6):
                    out_buf = (ctypes.c_ubyte * out_len)()
                    out_buf[0] = report_id
                    out_buf[1] = 0x02
                    out_buf[2] = 0x03
                    out_buf[3] = b3
                    out_buf[4] = b4
                    out_buf[5] = state_byte
                    if HidD_SetOutputReport(write_handle, ctypes.byref(out_buf), out_len):
                        output_success += 1
                        logger.debug(
                            "HID OutputReport profile RID=%02X b3=%02X b4=%02X (%s bytes): success",
                            report_id,
                            b3,
                            b4,
                            out_len,
                        )
                    else:
                        logger.debug(
                            "HID OutputReport profile RID=%02X b3=%02X b4=%02X (%s bytes): failed, err=%s",
                            report_id,
                            b3,
                            b4,
                            out_len,
                            ctypes.get_last_error(),
                        )

            total_success = write_success + output_success
            if total_success > 0:
                # Reflect commanded state locally so sync logic stays aligned
                # even if firmware does not echo a report for host-originated writes.
                self._last_state = is_muted
                self._last_state_ts = time()
                logger.info(
                    "HID Sync: Success mode=%s (WriteFile=%s, OutputReport=%s, profiles=%s)",
                    open_mode_used,
                    write_success,
                    output_success,
                    len(self._output_profiles),
                )
                return True
            else:
                logger.warning("HID Sync: All write methods failed")
                return False

        except Exception as e:
            logger.error("HID Sync Error: %s", e)
            return False
        finally:
            CloseHandle(write_handle)

    def _listen_loop(self):
        """Main read loop - independent from writes."""
        reconnect_delay = 1
        
        while self._running:
            if not self.device_path:
                self.device_path = self.find_device_path()
                if not self.device_path:
                    sleep(5)
                    continue

            # Open read handle (separate from write handle)
            with self._lock:
                if not self._handle:
                    self._handle = CreateFileW(
                        self.device_path,
                        GENERIC_READ,
                        SHARE_READ_WRITE,
                        None,
                        OPEN_EXISTING,
                        0,
                        None,
                    )

                    if self._handle != INVALID_HANDLE_VALUE:
                        logger.info("Cloud III HID: Connected for reading")
                        reconnect_delay = 1
                    else:
                        logger.debug("HID Discovery: Read handle open failed, err=%s", ctypes.get_last_error())
                        self._handle = None

            if not self._handle:
                sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)
                continue

            # Blocking read
            try:
                buf_len = 64
                read_buf = ctypes.create_string_buffer(buf_len)
                bytes_read = wintypes.DWORD(0)

                with self._lock:
                    handle = self._handle
                    
                success = ReadFile(handle, read_buf, buf_len, ctypes.byref(bytes_read), None)

                if not success:
                    err = ctypes.get_last_error()
                    logger.debug("HID Read failed, err=%s", err)
                    with self._lock:
                        if self._handle:
                            CloseHandle(self._handle)
                            self._handle = None
                    # If device got unplugged/re-enumerated, force discovery.
                    if err in (2, 3, 6, 1167):
                        self.device_path = None
                    sleep(1)
                    continue

                if bytes_read.value > 0:
                    data = bytes(read_buf.raw[:bytes_read.value])
                    if len(data) >= 6 and data[0] in (0x0C, 0x0D):
                        logger.debug("HID Report RID=%02x: %s (byte5=%02x)", data[0], data[:8].hex(), data[5])

                    if len(data) >= 6 and data[0] in (0x0C, 0x0D) and data[1:3] == b'\x02\x03':
                        is_muted = (data[5] == 0x01)
                        if is_muted != self._last_state:
                            logger.info("Cloud III Hardware/Button Report: Muted=%s (raw=%s)", is_muted, data[:6].hex())
                            self.volume_overlay.set_mic_mute_from_hardware(is_muted)
                            self._last_state = is_muted
                            self._last_state_ts = time()

            except Exception as e:
                logger.debug("HID Listen error: %s", e)
                with self._lock:
                    if self._handle:
                        CloseHandle(self._handle)
                        self._handle = None
                sleep(1)
