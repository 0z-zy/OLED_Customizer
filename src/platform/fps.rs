use std::fs;
use std::path::PathBuf;
use std::sync::{
    atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
    Arc, Mutex, RwLock,
};
use std::thread;
use std::time::Duration;

use libloading::{Library, Symbol};

use crate::config::app_data_dir;

static PRESENTMON_DLL: &[u8] = include_bytes!("../../assets/PresentMon.dll");

const STATUS_OK: i64 = 0;
const PRIVILEGES_ERROR: i64 = 1007;

type FnStartRecording = unsafe extern "C" fn(i64, i64) -> i64;
type FnStopRecording = unsafe extern "C" fn() -> i64;
type FnGetCurrentData = unsafe extern "C" fn(i64, *mut f64, *mut f64, *mut i64) -> i64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FpsStatus {
    Off,
    Active,
    NeedsAdmin,
    Error(String),
}

impl FpsStatus {
    pub fn label(&self) -> String {
        match self {
            FpsStatus::Off => "Off".to_string(),
            FpsStatus::Active => "Active".to_string(),
            FpsStatus::NeedsAdmin => "Needs Admin".to_string(),
            FpsStatus::Error(e) => e.clone(),
        }
    }
}

struct Inner {
    lib: Option<Library>,
    start_fn: Option<FnStartRecording>,
    stop_fn: Option<FnStopRecording>,
    get_fn: Option<FnGetCurrentData>,
}

unsafe impl Send for Inner {}

pub struct FpsMonitor {
    inner: Arc<Mutex<Inner>>,
    fps_value: Arc<AtomicU32>,
    running: Arc<AtomicBool>,
    worker_gen: Arc<AtomicU64>,
    status: Arc<RwLock<FpsStatus>>,
}

impl FpsMonitor {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner {
                lib: None,
                start_fn: None,
                stop_fn: None,
                get_fn: None,
            })),
            fps_value: Arc::new(AtomicU32::new(0)),
            running: Arc::new(AtomicBool::new(false)),
            worker_gen: Arc::new(AtomicU64::new(0)),
            status: Arc::new(RwLock::new(FpsStatus::Off)),
        }
    }

    pub fn set_enabled(&self, enabled: bool) {
        if enabled {
            if !self.running.load(Ordering::Relaxed) {
                self.start();
            }
        } else if self.running.load(Ordering::Relaxed) || *self.status.read().unwrap() != FpsStatus::Off {
            self.stop();
        }
    }

    pub fn get_fps(&self) -> u32 {
        self.fps_value.load(Ordering::Relaxed)
    }

    pub fn status(&self) -> FpsStatus {
        self.status.read().unwrap().clone()
    }

    fn ensure_dll_extracted() -> Result<PathBuf, String> {
        let dir = app_data_dir();
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let dll_path = dir.join("PresentMon.dll");
        let need_write = match fs::metadata(&dll_path) {
            Ok(m) => m.len() != PRESENTMON_DLL.len() as u64,
            Err(_) => true,
        };
        if need_write {
            if let Err(e) = fs::write(&dll_path, PRESENTMON_DLL) {
                if !dll_path.exists() {
                    return Err(format!("Extract PresentMon.dll failed: {}", e));
                }
            }
        }
        Ok(dll_path)
    }

    pub fn start(&self) {
        if self.running.load(Ordering::Relaxed) {
            return;
        }

        let dll_path = match Self::ensure_dll_extracted() {
            Ok(p) => p,
            Err(e) => {
                log::error!("FPSMonitor: {}", e);
                *self.status.write().unwrap() = FpsStatus::Error(e);
                return;
            }
        };

        let start_res = {
            let mut guard = self.inner.lock().unwrap();
            if guard.lib.is_none() {
                unsafe {
                    match Library::new(&dll_path) {
                        Ok(lib) => {
                            let start_s: Result<Symbol<FnStartRecording>, _> =
                                lib.get(b"StartEventRecording\0");
                            let stop_s: Result<Symbol<FnStopRecording>, _> =
                                lib.get(b"StopEventRecording\0");
                            let get_s: Result<Symbol<FnGetCurrentData>, _> =
                                lib.get(b"GetCurrentData\0");
                            match (start_s, stop_s, get_s) {
                                (Ok(st), Ok(sp), Ok(gt)) => {
                                    guard.start_fn = Some(*st);
                                    guard.stop_fn = Some(*sp);
                                    guard.get_fn = Some(*gt);
                                    guard.lib = Some(lib);
                                }
                                _ => {
                                    *self.status.write().unwrap() =
                                        FpsStatus::Error("Missing PresentMon exports".into());
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            *self.status.write().unwrap() =
                                FpsStatus::Error(format!("Load DLL failed: {}", e));
                            return;
                        }
                    }
                }
            }

            if let Some(start_fn) = guard.start_fn {
                unsafe { start_fn(0, 86400) }
            } else {
                -1
            }
        };

        if start_res == PRIVILEGES_ERROR {
            log::warn!("FPSMonitor: PresentMon requires Administrator privileges (error 1007)");
            *self.status.write().unwrap() = FpsStatus::NeedsAdmin;
            return;
        }
        if start_res != STATUS_OK {
            log::error!("FPSMonitor: StartEventRecording failed (code {})", start_res);
            *self.status.write().unwrap() =
                FpsStatus::Error(format!("Error {}", start_res));
            return;
        }

        self.running.store(true, Ordering::Relaxed);
        *self.status.write().unwrap() = FpsStatus::Active;
        let gen = self.worker_gen.fetch_add(1, Ordering::Relaxed) + 1;

        let inner = self.inner.clone();
        let fps_val = self.fps_value.clone();
        let running = self.running.clone();
        let worker_gen = self.worker_gen.clone();

        thread::Builder::new()
            .name("FPS-DLL-Worker".to_string())
            .spawn(move || {
                let mut data_buf = [0.0f64; 6];
                let mut time_buf = [0.0f64; 1];
                let mut size_buf: i64 = 0;

                while running.load(Ordering::Relaxed)
                    && worker_gen.load(Ordering::Relaxed) == gen
                {
                    let val = {
                        let guard = inner.lock().unwrap();
                        if let Some(get_fn) = guard.get_fn {
                            unsafe {
                                let res = get_fn(
                                    1,
                                    data_buf.as_mut_ptr(),
                                    time_buf.as_mut_ptr(),
                                    &mut size_buf,
                                );
                                if res == STATUS_OK && size_buf > 0 && data_buf[0].is_finite() {
                                    data_buf[0].round().clamp(0.0, 9999.0) as u32
                                } else {
                                    0
                                }
                            }
                        } else {
                            0
                        }
                    };
                    fps_val.store(val, Ordering::Relaxed);
                    thread::sleep(Duration::from_millis(500));
                }
            })
            .ok();

        log::info!("FPSMonitor: Native PresentMon started");
    }

    pub fn stop(&self) {
        self.running.store(false, Ordering::Relaxed);
        self.worker_gen.fetch_add(1, Ordering::Relaxed);
        self.fps_value.store(0, Ordering::Relaxed);
        *self.status.write().unwrap() = FpsStatus::Off;

        if let Ok(guard) = self.inner.lock() {
            if let Some(stop_fn) = guard.stop_fn {
                unsafe {
                    let _ = stop_fn();
                }
            }
        }
    }
}

impl Drop for FpsMonitor {
    fn drop(&mut self) {
        self.stop();
    }
}
