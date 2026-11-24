use std::ffi::{c_char, c_int, c_uint, CStr};
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc, RwLock,
};
use std::thread;
use std::time::{Duration, Instant};

use libloading::{Library, Symbol};
use windows::Win32::Foundation::FILETIME;
use windows::Win32::System::ProcessStatus::{
    GetProcessMemoryInfo, K32EmptyWorkingSet, PROCESS_MEMORY_COUNTERS,
};
use windows::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
use windows::Win32::System::Threading::{GetCurrentProcess, GetSystemTimes};

use crate::oled::views::hw_monitor::HwStats;
use crate::platform::cpu_temp::CpuTempReader;
use crate::platform::fps::FpsMonitor;

#[repr(C)]
struct NvmlUtilization {
    gpu: c_uint,
    memory: c_uint,
}

type NvmlDevice = *mut std::ffi::c_void;
type FnInit = unsafe extern "C" fn() -> c_int;
type FnGetHandle = unsafe extern "C" fn(c_uint, *mut NvmlDevice) -> c_int;
type FnGetName = unsafe extern "C" fn(NvmlDevice, *mut c_char, c_uint) -> c_int;
type FnGetTemp = unsafe extern "C" fn(NvmlDevice, c_uint, *mut c_uint) -> c_int;
type FnGetUtil = unsafe extern "C" fn(NvmlDevice, *mut NvmlUtilization) -> c_int;

struct NvmlReader {
    _lib: Library,
    device: NvmlDevice,
    name: String,
    get_temp: FnGetTemp,
    get_util: FnGetUtil,
}

unsafe impl Send for NvmlReader {}

impl NvmlReader {
    fn try_load() -> Option<Self> {
        unsafe {
            let lib = Library::new(r"C:\Windows\System32\nvml.dll").ok()?;
            let init: Symbol<FnInit> = lib.get(b"nvmlInit_v2\0").ok()?;
            if init() != 0 {
                return None;
            }
            let get_handle: Symbol<FnGetHandle> =
                lib.get(b"nvmlDeviceGetHandleByIndex_v2\0").ok()?;
            let mut dev: NvmlDevice = std::ptr::null_mut();
            if get_handle(0, &mut dev) != 0 || dev.is_null() {
                return None;
            }
            let mut name_buf = [0i8; 96];
            let mut gpu_name = "NVIDIA GPU".to_string();
            if let Ok(get_name) = lib.get::<FnGetName>(b"nvmlDeviceGetName\0") {
                if get_name(dev, name_buf.as_mut_ptr(), 96) == 0 {
                    gpu_name = CStr::from_ptr(name_buf.as_ptr())
                        .to_string_lossy()
                        .into_owned();
                }
            }
            let get_temp = *lib.get::<FnGetTemp>(b"nvmlDeviceGetTemperature\0").ok()?;
            let get_util = *lib.get::<FnGetUtil>(b"nvmlDeviceGetUtilizationRates\0").ok()?;
            Some(Self {
                _lib: lib,
                device: dev,
                name: gpu_name,
                get_temp,
                get_util,
            })
        }
    }

    fn read(&self) -> (Option<i32>, Option<u8>) {
        unsafe {
            let mut temp = 0u32;
            let t = if (self.get_temp)(self.device, 0, &mut temp) == 0 {
                Some(temp as i32)
            } else {
                None
            };
            let mut util = NvmlUtilization { gpu: 0, memory: 0 };
            let u = if (self.get_util)(self.device, &mut util) == 0 {
                Some(util.gpu.min(100) as u8)
            } else {
                None
            };
            (t, u)
        }
    }
}

pub fn process_memory_mb() -> f32 {
    unsafe {
        let mut pmc = PROCESS_MEMORY_COUNTERS::default();
        pmc.cb = std::mem::size_of::<PROCESS_MEMORY_COUNTERS>() as u32;
        if GetProcessMemoryInfo(GetCurrentProcess(), &mut pmc, pmc.cb).is_ok() {
            pmc.WorkingSetSize as f32 / (1024.0 * 1024.0)
        } else {
            0.0
        }
    }
}

pub fn trim_working_set() {
    unsafe {
        let _ = K32EmptyWorkingSet(GetCurrentProcess());
    }
}

#[inline]
fn ft_to_u64(ft: FILETIME) -> u64 {
    ((ft.dwHighDateTime as u64) << 32) | (ft.dwLowDateTime as u64)
}

fn read_system_times() -> Option<(u64, u64, u64)> {
    unsafe {
        let mut idle = FILETIME::default();
        let mut kernel = FILETIME::default();
        let mut user = FILETIME::default();
        if GetSystemTimes(Some(&mut idle), Some(&mut kernel), Some(&mut user)).is_ok() {
            Some((ft_to_u64(idle), ft_to_u64(kernel), ft_to_u64(user)))
        } else {
            None
        }
    }
}

fn read_memory_gb() -> (f32, f32, u8) {
    unsafe {
        let mut ms = MEMORYSTATUSEX::default();
        ms.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        if GlobalMemoryStatusEx(&mut ms).is_ok() && ms.ullTotalPhys > 0 {
            let total_gb = ms.ullTotalPhys as f32 / (1024.0 * 1024.0 * 1024.0);
            let used_bytes = ms.ullTotalPhys.saturating_sub(ms.ullAvailPhys);
            let used_gb = used_bytes as f32 / (1024.0 * 1024.0 * 1024.0);
            let pct = ms.dwMemoryLoad.min(100) as u8;
            (used_gb, total_gb, pct)
        } else {
            (0.0, 0.0, 0)
        }
    }
}

pub fn start_hw_poller(
    shared: Arc<RwLock<HwStats>>,
    polling_ms: Arc<AtomicU64>,
    show_fps: Arc<AtomicBool>,
    fps_monitor: Arc<FpsMonitor>,
    stop: Arc<AtomicBool>,
) {
    thread::Builder::new()
        .name("HW-Poller".to_string())
        .spawn(move || {
            let nvml = NvmlReader::try_load();
            if let Some(ref n) = nvml {
                log::info!("NVML initialized: {}", n.name);
            }
            let cpu_temp_reader = CpuTempReader::start(
                polling_ms.load(Ordering::Relaxed),
                nvml.is_some(),
            );

            let mut prev_times = read_system_times();
            let lhm_agent = ureq::AgentBuilder::new()
                .timeout_connect(Duration::from_millis(120))
                .timeout_read(Duration::from_millis(180))
                .build();
            let mut last_lhm_try = Instant::now() - Duration::from_secs(30);
            let mut lhm_reachable = false;

            while !stop.load(Ordering::Relaxed) {
                let mut cpu_load = 0u8;
                if let Some((idle, kernel, user)) = read_system_times() {
                    if let Some((p_idle, p_kernel, p_user)) = prev_times {
                        let d_idle = idle.saturating_sub(p_idle);
                        let d_total = kernel.saturating_sub(p_kernel) + user.saturating_sub(p_user);
                        if d_total > 0 {
                            let busy = d_total.saturating_sub(d_idle) as f32 / d_total as f32;
                            cpu_load = (busy * 100.0).round().clamp(0.0, 100.0) as u8;
                        }
                    }
                    prev_times = Some((idle, kernel, user));
                }

                let (used_gb, total_gb, ram_pct) = read_memory_gb();
                let helper = cpu_temp_reader.read();
                let mut cpu_temp = helper.cpu_temp_c;

                if cpu_temp.is_none()
                    && (lhm_reachable || last_lhm_try.elapsed() >= Duration::from_secs(5))
                {
                    last_lhm_try = Instant::now();
                    if let Ok(resp) = lhm_agent.get("http://127.0.0.1:8085/data.json").call() {
                        if let Ok(val) = resp.into_json::<serde_json::Value>() {
                            lhm_reachable = true;
                            cpu_temp = find_lhm_cpu_temp(&val);
                        }
                    } else {
                        lhm_reachable = false;
                    }
                }

                let (gpu_name, gpu_temp, gpu_load) = if let Some(ref n) = nvml {
                    let (t, u) = n.read();
                    (
                        n.name.clone(),
                        t.or(helper.gpu_temp_c),
                        u.or(helper.gpu_load_pct),
                    )
                } else {
                    ("GPU".to_string(), helper.gpu_temp_c, helper.gpu_load_pct)
                };

                let fps_enabled = show_fps.load(Ordering::Relaxed);
                let (fps, fps_status) = if fps_enabled {
                    (Some(fps_monitor.get_fps()), fps_monitor.status().label())
                } else {
                    (None, "Off".to_string())
                };

                let stats = HwStats {
                    cpu_temp_c: cpu_temp,
                    cpu_load_pct: cpu_load,
                    gpu_name,
                    gpu_temp_c: gpu_temp,
                    gpu_load_pct: gpu_load,
                    ram_used_gb: used_gb,
                    ram_total_gb: total_gb,
                    ram_pct,
                    fps,
                    show_fps: fps_enabled,
                    fps_status,
                };

                if let Ok(mut w) = shared.write() {
                    *w = stats;
                }

                let ms = polling_ms.load(Ordering::Relaxed).clamp(250, 10000);
                thread::sleep(Duration::from_millis(ms));
            }

            cpu_temp_reader.stop();
        })
        .expect("spawn HW-Poller");
}

fn find_lhm_cpu_temp(val: &serde_json::Value) -> Option<i32> {
    if let Some(obj) = val.as_object() {
        let text = obj.get("Text").and_then(|v| v.as_str()).unwrap_or("");
        if text.contains("Tctl") || text.contains("Package") || text.contains("CPU") {
            if let Some(val_str) = obj.get("Value").and_then(|v| v.as_str()) {
                if val_str.contains("°C") || val_str.contains('C') {
                    let num: String = val_str
                        .chars()
                        .take_while(|c| c.is_ascii_digit() || *c == '.')
                        .collect();
                    if let Ok(f) = num.parse::<f32>() {
                        return Some(f.round() as i32);
                    }
                }
            }
        }
        if let Some(children) = obj.get("Children").and_then(|v| v.as_array()) {
            for c in children {
                if let Some(t) = find_lhm_cpu_temp(c) {
                    return Some(t);
                }
            }
        }
    }
    None
}
