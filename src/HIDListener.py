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
        self._last_hw_ts = 0.0      # time of last physical/accepted report
        self._last_write_ts = 0.0   # time of last host-originated write
        self._suppress_until = 0.0  # silence initial chatter
        self._latched_profile_index = None  # Sticky index of working HID profile
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
        issued_at = time()
        t = threading.Thread(target=self._do_hardware_mute, args=(is_muted, issued_at))
        t.daemon = True
        t.start()

    def _do_hardware_mute(self, is_muted, issued_at=None):
        """
        Write mute command to headset.
        Strategy: Use a completely separate handle for writing.
        """
        if issued_at is None:
            issued_at = time()

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
            # Guard against stale host writes arriving after a newer physical button event.
            with self._lock:
                latest_hw_state = self._last_state
                latest_hw_ts = self._last_hw_ts
            if (
                latest_hw_state is not None
                and latest_hw_ts > issued_at
                and latest_hw_state != is_muted
            ):
                logger.info(
                    "HID Sync: Skipping stale write mute=%s (newer hardware state=%s)",
                    is_muted,
                    latest_hw_state,
                )
                return False

            # Update current knowledge of state BEFORE we start the long pulsatile write loop.
            # This ensures that any incoming HID reports (the "echo" from the headset)
            # are correctly identified as flutter/known-state and ignored by the debounce.
            with self._lock:
                # If we ALREADY think the hardware is in the desired state,
                # skip the long write cycle entirely to avoid firmware overwhelm/loops.
                if self._last_state == is_muted:
                    logger.debug("HID Sync: Hardware already in state %s, skipping write", is_muted)
                    return True

                if self._last_hw_ts <= issued_at:
                    self._last_state = is_muted
                    self._last_write_ts = time()

            logger.info("HID Sync: Sending mute=%s to headset", is_muted)
            state_byte = 0x01 if is_muted else 0x00
            write_success = 0
            output_success = 0

            # Profile Latching Logic:
            # If we already have a latched index, try it first.
            profiles_to_try = self._output_profiles
            if self._latched_profile_index is not None:
                idx = self._latched_profile_index
                profiles_to_try = [self._output_profiles[idx]] + [p for i, p in enumerate(self._output_profiles) if i != idx]

            for idx_in_subset, (report_id, b3, b4) in enumerate(profiles_to_try):
                report = bytearray(64)
                report[0] = report_id
                report[1] = 0x02
                report[2] = 0x03
                report[3] = b3
                report[4] = b4
                report[5] = state_byte

                # Send exactly one pulse per profile (WriteFile path)
                bytes_written = wintypes.DWORD(0)
                if WriteFile(write_handle, bytes(report), 64, ctypes.byref(bytes_written), None):
                    write_success = 1
                else:
                    # Try HidD_SetOutputReport only if WriteFile failed
                    out_buf = (ctypes.c_ubyte * 64)()
                    for idx_buf in range(6): out_buf[idx_buf] = report[idx_buf]
                    if HidD_SetOutputReport(write_handle, ctypes.byref(out_buf), 64):
                        output_success = 1

                if (write_success + output_success) > 0:
                    # LATCH SUCCESS: If this was a new discovery, save it.
                    if self._latched_profile_index is None:
                        # Find the actual original index
                        for orig_idx, p in enumerate(self._output_profiles):
                            if p == (report_id, b3, b4):
                                self._latched_profile_index = orig_idx
                                logger.info("HID Sync: Profile latched to index %s (RID=%02X)", orig_idx, report_id)
                                break
                    # STOP: Don't send to other profiles. Sending to multiple (e.g. 0x0D and 0x0C)
                    # can trigger a "double-tap" toggle in firmware, starting a loop.
                    break

            if (write_success + output_success) > 0:
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
                            now = time()
                            
                            # 0. Initial Sync Settle: Ignore reports during startup/connection flurry
                            if now < self._suppress_until:
                                logger.debug("HID Debounce: Ignoring initial connection chatter -> Muted=%s", is_muted)
                                continue

                            # 1. Flutter Debounce: Ignore consecutive HW reports within 150ms
                            if (now - self._last_hw_ts) < 0.15:
                                logger.debug("HID Debounce: Ignoring hardware flutter (150ms) -> Muted=%s", is_muted)
                                continue

                            # 2. Echo Debounce: Ignore reports that closely follow a host command (400ms)
                            if (now - self._last_write_ts) < 0.4:
                                logger.debug("HID Debounce: Ignoring command echo (400ms) -> Muted=%s", is_muted)
                                continue

                            # Update trackers - DisplayManager's RPC loop will pick this up
                            # and handle the master sync (OLED + Discord + System Mic).
                            self._last_state = is_muted
                            self._last_hw_ts = now
                            logger.info("Cloud III Hardware/Button Report: Muted=%s (raw=%s)", is_muted, data[:6].hex())

            except Exception as e:
                logger.debug("HID Listen error: %s", e)
                with self._lock:
                    if self._handle:
                        CloseHandle(self._handle)
                        self._handle = None
                sleep(1)
