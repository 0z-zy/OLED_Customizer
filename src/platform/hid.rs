use std::ffi::OsStr;
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::sync::{
    atomic::{AtomicBool, AtomicIsize, Ordering},
    mpsc::Sender,
    Arc, Mutex, RwLock,
};
use std::thread;
use std::time::{Duration, Instant};

use libloading::Library;
use windows::core::PCWSTR;
use windows::Win32::Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE};
use windows::Win32::Storage::FileSystem::{
    CreateFileW, ReadFile, WriteFile, FILE_FLAGS_AND_ATTRIBUTES, FILE_SHARE_READ,
    FILE_SHARE_WRITE, OPEN_EXISTING,
};
use windows::Win32::System::Registry::{
    RegCloseKey, RegEnumKeyExW, RegOpenKeyExW, HKEY, HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY,
};
use windows::Win32::System::IO::CancelIoEx;

use crate::platform::audio::AudioCommand;

const HID_GUID: &str = "{4d1e55b2-f16f-11cf-88cb-001111000030}";
const GENERIC_READ: u32 = 0x80000000;
const GENERIC_WRITE: u32 = 0x40000000;
const DEVICE_MARKERS: [&str; 4] = ["VID_03F0", "VID_0951", "HYPERX", "CLOUD"];
const BATTERY_STALE_SECS: u64 = 150;

fn to_wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

fn candidate_priority(path: &str) -> u8 {
    let u = path.to_ascii_uppercase();
    if u.contains("COL05") {
        0
    } else if u.contains("COL04") {
        1
    } else if u.contains("COL06") {
        2
    } else if u.contains("COL") {
        3
    } else {
        4
    }
}

fn build_candidate_paths(device_instance_key: &str, ref_name: Option<&str>) -> Vec<String> {
    let base = device_instance_key.replace("##?#", "\\\\?\\");
    let mut out = vec![base.clone()];
    if let Some(r) = ref_name {
        if !r.is_empty() {
            out.push(format!("{}\\{}", base, r));
        }
    }
    out
}

unsafe fn enum_subkeys(hkey: HKEY) -> Vec<String> {
    let mut keys = Vec::new();
    let mut idx = 0u32;
    let mut buf = [0u16; 512];
    loop {
        let mut len = buf.len() as u32;
        let res = RegEnumKeyExW(
            hkey,
            idx,
            windows::core::PWSTR(buf.as_mut_ptr()),
            &mut len,
            None,
            windows::core::PWSTR::null(),
            None,
            None,
        );
        if res.is_err() {
            break;
        }
        let s = std::ffi::OsString::from_wide(&buf[..len as usize])
            .to_string_lossy()
            .into_owned();
        keys.push(s);
        idx += 1;
    }
    keys
}

fn can_open(path: &str, access: u32) -> bool {
    let w = to_wide(path);
    unsafe {
        let h = CreateFileW(
            PCWSTR(w.as_ptr()),
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAGS_AND_ATTRIBUTES(0),
            None,
        );
        match h {
            Ok(handle) if handle != INVALID_HANDLE_VALUE => {
                let _ = CloseHandle(handle);
                true
            }
            _ => false,
        }
    }
}

pub fn find_hyperx_hid_path() -> Option<String> {
    let class_path = format!("SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{}", HID_GUID);
    let class_w = to_wide(&class_path);
    let mut root_key = HKEY::default();

    unsafe {
        if RegOpenKeyExW(
            HKEY_LOCAL_MACHINE,
            PCWSTR(class_w.as_ptr()),
            0,
            KEY_READ | KEY_WOW64_64KEY,
            &mut root_key,
        )
        .is_err()
        {
            return None;
        }

        let instances = enum_subkeys(root_key);
        let mut candidates = Vec::new();

        for inst in instances {
            let up = inst.to_ascii_uppercase();
            if !DEVICE_MARKERS.iter().any(|m| up.contains(m)) {
                continue;
            }
            for p in build_candidate_paths(&inst, None) {
                if !candidates.contains(&p) {
                    candidates.push(p);
                }
            }
            let inst_w = to_wide(&inst);
            let mut dev_key = HKEY::default();
            if RegOpenKeyExW(
                root_key,
                PCWSTR(inst_w.as_ptr()),
                0,
                KEY_READ | KEY_WOW64_64KEY,
                &mut dev_key,
            )
            .is_ok()
            {
                for r in enum_subkeys(dev_key) {
                    for p in build_candidate_paths(&inst, Some(&r)) {
                        if !candidates.contains(&p) {
                            candidates.push(p);
                        }
                    }
                }
                let _ = RegCloseKey(dev_key);
            }
        }

        let _ = RegCloseKey(root_key);

        candidates.sort_by_key(|p| candidate_priority(p));
        let mut best: Option<(u8, String)> = None;
        for c in candidates {
            let r_ok = can_open(&c, GENERIC_READ);
            let w_ok = can_open(&c, GENERIC_WRITE);
            if !r_ok && !w_ok {
                continue;
            }
            let score = if r_ok && w_ok {
                2
            } else if r_ok {
                1
            } else {
                0
            };
            if score == 2 && c.to_ascii_uppercase().contains("COL05") {
                return Some(c);
            }
            if best.as_ref().map(|b| score > b.0).unwrap_or(true) {
                best = Some((score, c));
            }
        }
        best.map(|b| b.1)
    }
}

pub struct HeadsetHid {
    enabled: AtomicBool,
    running: Arc<AtomicBool>,
    battery: Arc<RwLock<Option<(u8, Instant)>>>,
    device_path: Arc<RwLock<Option<String>>>,
    status_text: Arc<RwLock<String>>,
    read_handle: Arc<Mutex<AtomicIsize>>,
    audio_tx: Sender<AudioCommand>,
}

impl HeadsetHid {
    pub fn new(audio_tx: Sender<AudioCommand>) -> Self {
        Self {
            enabled: AtomicBool::new(false),
            running: Arc::new(AtomicBool::new(false)),
            battery: Arc::new(RwLock::new(None)),
            device_path: Arc::new(RwLock::new(None)),
            status_text: Arc::new(RwLock::new("Disabled".to_string())),
            read_handle: Arc::new(Mutex::new(AtomicIsize::new(0))),
            audio_tx,
        }
    }

    pub fn set_enabled(&self, enabled: bool) {
        let was = self.enabled.swap(enabled, Ordering::Relaxed);
        if enabled && !was {
            self.start();
        } else if !enabled && was {
            self.stop();
        }
    }

    pub fn current_battery(&self) -> Option<u8> {
        if !self.enabled.load(Ordering::Relaxed) {
            return None;
        }
        let guard = self.battery.read().unwrap();
        if let Some((pct, ts)) = *guard {
            if ts.elapsed() <= Duration::from_secs(BATTERY_STALE_SECS) {
                return Some(pct);
            }
        }
        None
    }

    pub fn status_summary(&self) -> String {
        if !self.enabled.load(Ordering::Relaxed) {
            return "Disabled".to_string();
        }
        if let Some(pct) = self.current_battery() {
            return format!("Connected • {}%", pct);
        }
        self.status_text.read().unwrap().clone()
    }

    fn start(&self) {
        if self.running.swap(true, Ordering::Relaxed) {
            return;
        }
        *self.status_text.write().unwrap() = "Searching for HyperX headset...".to_string();

        let running_l = self.running.clone();
        let battery_l = self.battery.clone();
        let path_l = self.device_path.clone();
        let status_l = self.status_text.clone();
        let handle_l = self.read_handle.clone();
        let audio_tx = self.audio_tx.clone();

        thread::Builder::new()
            .name("HID-Listen".to_string())
            .spawn(move || {
                let mut reconnect_delay = 1u64;
                while running_l.load(Ordering::Relaxed) {
                    let cur_path = {
                        let existing = path_l.read().unwrap().clone();
                        if existing.is_some() {
                            existing
                        } else {
                            let found = find_hyperx_hid_path();
                            *path_l.write().unwrap() = found.clone();
                            found
                        }
                    };

                    let Some(dev_path) = cur_path else {
                        *status_l.write().unwrap() = "Searching for HyperX headset...".to_string();
                        thread::sleep(Duration::from_secs(4));
                        continue;
                    };

                    let w_path = to_wide(&dev_path);
                    let handle = unsafe {
                        CreateFileW(
                            PCWSTR(w_path.as_ptr()),
                            GENERIC_READ,
                            FILE_SHARE_READ | FILE_SHARE_WRITE,
                            None,
                            OPEN_EXISTING,
                            FILE_FLAGS_AND_ATTRIBUTES(0),
                            None,
                        )
                    };

                    let Ok(h) = handle else {
                        *status_l.write().unwrap() = "Waiting for headset HID...".to_string();
                        thread::sleep(Duration::from_secs(reconnect_delay));
                        reconnect_delay = (reconnect_delay * 2).min(15);
                        continue;
                    };

                    reconnect_delay = 1;
                    handle_l
                        .lock()
                        .unwrap()
                        .store(h.0 as isize, Ordering::Relaxed);
                    *status_l.write().unwrap() =
                        "Connected (waiting for battery reply...)".to_string();
                    let opened_at = Instant::now();
                    let mut last_hw_state: Option<bool> = None;
                    let mut last_hw_event = Instant::now() - Duration::from_secs(10);

                    let mut buf = [0u8; 64];
                    let mut bytes_read = 0u32;

                    while running_l.load(Ordering::Relaxed) {
                        let ok = unsafe {
                            ReadFile(h, Some(&mut buf), Some(&mut bytes_read), None).is_ok()
                        };
                        if !ok {
                            break;
                        }
                        let n = bytes_read as usize;
                        // Battery reply: 0c 02 03 01 00 06 <pct> <flag>
                        if n >= 7
                            && buf[0] == 0x0C
                            && buf[1..6] == [0x02, 0x03, 0x01, 0x00, 0x06]
                            && buf[6] <= 100
                        {
                            *battery_l.write().unwrap() = Some((buf[6], Instant::now()));
                            *status_l.write().unwrap() = format!("Connected • {}%", buf[6]);
                            continue;
                        }

                        // Physical mute button: 0d 02 03 .. (0x05 | 0x03) (0x00 | 0x01)
                        if n >= 6
                            && buf[0] == 0x0D
                            && buf[1..3] == [0x02, 0x03]
                            && (buf[4] == 0x05 || buf[4] == 0x03)
                            && buf[5] <= 1
                        {
                            let is_muted = buf[5] == 1;
                            if last_hw_state.is_none() {
                                last_hw_state = Some(is_muted);
                                if opened_at.elapsed() > Duration::from_secs(3) {
                                    last_hw_event = Instant::now();
                                    let _ = audio_tx.send(AudioCommand::SetMicMute(is_muted));
                                }
                                continue;
                            }
                            if Some(is_muted) != last_hw_state
                                && opened_at.elapsed() >= Duration::from_secs(2)
                                && last_hw_event.elapsed() >= Duration::from_millis(150)
                            {
                                last_hw_state = Some(is_muted);
                                last_hw_event = Instant::now();
                                let _ = audio_tx.send(AudioCommand::SetMicMute(is_muted));
                            }
                        }
                    }

                    unsafe {
                        let _ = CloseHandle(h);
                    }
                    handle_l.lock().unwrap().store(0, Ordering::Relaxed);
                    *path_l.write().unwrap() = None;
                    thread::sleep(Duration::from_secs(1));
                }
            })
            .ok();

        let running_b = self.running.clone();
        let path_b = self.device_path.clone();
        thread::Builder::new()
            .name("HID-Battery".to_string())
            .spawn(move || {
                thread::sleep(Duration::from_secs(2));
                while running_b.load(Ordering::Relaxed) {
                    if let Some(ref dev_path) = *path_b.read().unwrap() {
                        query_battery_report(dev_path);
                    }
                    for _ in 0..60 {
                        if !running_b.load(Ordering::Relaxed) {
                            return;
                        }
                        thread::sleep(Duration::from_secs(1));
                    }
                }
            })
            .ok();
    }

    pub fn stop(&self) {
        self.running.store(false, Ordering::Relaxed);
        let raw = self.read_handle.lock().unwrap().swap(0, Ordering::Relaxed);
        if raw != 0 {
            unsafe {
                let h = HANDLE(raw as *mut std::ffi::c_void);
                let _ = CancelIoEx(h, None);
                let _ = CloseHandle(h);
            }
        }
        *self.battery.write().unwrap() = None;
        *self.status_text.write().unwrap() = "Disabled".to_string();
    }
}

impl Drop for HeadsetHid {
    fn drop(&mut self) {
        self.stop();
    }
}

fn query_battery_report(dev_path: &str) {
    let w = to_wide(dev_path);
    unsafe {
        let mut h = CreateFileW(
            PCWSTR(w.as_ptr()),
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAGS_AND_ATTRIBUTES(0),
            None,
        );
        if h.is_err() {
            h = CreateFileW(
                PCWSTR(w.as_ptr()),
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAGS_AND_ATTRIBUTES(0),
                None,
            );
        }
        let Ok(handle) = h else {
            return;
        };

        let mut report = [0u8; 64];
        report[0..6].copy_from_slice(&[0x0C, 0x02, 0x03, 0x01, 0x00, 0x06]);
        let mut written = 0u32;
        if WriteFile(handle, Some(&report), Some(&mut written), None).is_err() {
            if let Ok(hid_lib) = Library::new("hid.dll") {
                type FnSetOut = unsafe extern "system" fn(HANDLE, *const u8, u32) -> u8;
                if let Ok(func) = hid_lib.get::<FnSetOut>(b"HidD_SetOutputReport\0") {
                    let _ = func(handle, report.as_ptr(), 64);
                }
            }
        }
        let _ = CloseHandle(handle);
    }
}
