use std::fs;
use std::io::{BufRead, BufReader};
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex, RwLock,
};
use std::thread;

use crate::config::app_data_dir;
use crate::platform::startup::is_running_as_admin;

static SENSORS_EXE: &[u8] = include_bytes!("../../assets/sensors/oled_sensors.exe");
static LHM_DLL: &[u8] = include_bytes!("../../assets/sensors/LibreHardwareMonitorLib.dll");

const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone, Debug, Default)]
pub struct SensorHelperData {
    pub cpu_temp_c: Option<i32>,
    pub gpu_temp_c: Option<i32>,
    pub gpu_load_pct: Option<u8>,
}

pub struct CpuTempReader {
    data: Arc<RwLock<SensorHelperData>>,
    stop_flag: Arc<AtomicBool>,
    child: Arc<Mutex<Option<(Child, Option<ChildStdin>)>>>,
}

impl CpuTempReader {
    pub fn start(interval_ms: u64, nvml_available: bool) -> Self {
        let data = Arc::new(RwLock::new(SensorHelperData::default()));
        let stop_flag = Arc::new(AtomicBool::new(false));
        let child = Arc::new(Mutex::new(None));

        // Skip spawning .NET helper completely when non-admin (LHM cannot read Ryzen CPU temps without Admin)
        if !is_running_as_admin() {
            return Self {
                data,
                stop_flag,
                child,
            };
        }

        if let Ok(exe_path) = Self::ensure_extracted() {
            let mut cmd = Command::new(&exe_path);
            cmd.arg(interval_ms.clamp(250, 10000).to_string());
            if nvml_available {
                cmd.arg("--no-gpu");
            }
            cmd.stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null())
                .creation_flags(CREATE_NO_WINDOW);

            if let Some(parent) = exe_path.parent() {
                cmd.current_dir(parent);
            }

            if let Ok(mut proc) = cmd.spawn() {
                let stdout = proc.stdout.take();
                let stdin = proc.stdin.take();
                *child.lock().unwrap() = Some((proc, stdin));

                let data_c = data.clone();
                let stop_c = stop_flag.clone();
                if let Some(out) = stdout {
                    thread::Builder::new()
                        .name("LHM-Helper-Reader".to_string())
                        .spawn(move || {
                            let reader = BufReader::new(out);
                            for line in reader.lines().map_while(Result::ok) {
                                if stop_c.load(Ordering::Relaxed) {
                                    break;
                                }
                                if let Ok(v) = serde_json::from_str::<serde_json::Value>(&line) {
                                    let cpu = v
                                        .get("cpu_temp")
                                        .and_then(|x| x.as_f64())
                                        .map(|f| f.round() as i32);
                                    let gput = v
                                        .get("gpu_temp")
                                        .and_then(|x| x.as_f64())
                                        .map(|f| f.round() as i32);
                                    let gpul = v
                                        .get("gpu_load")
                                        .and_then(|x| x.as_f64())
                                        .map(|f| f.round().clamp(0.0, 100.0) as u8);
                                    if let Ok(mut w) = data_c.write() {
                                        w.cpu_temp_c = cpu;
                                        w.gpu_temp_c = gput;
                                        w.gpu_load_pct = gpul;
                                    }
                                }
                            }
                        })
                        .ok();
                }
            }
        }

        Self {
            data,
            stop_flag,
            child,
        }
    }

    fn ensure_extracted() -> Result<PathBuf, String> {
        let dir = app_data_dir().join("sensors");
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let exe_path = dir.join("oled_sensors.exe");
        let dll_path = dir.join("LibreHardwareMonitorLib.dll");

        for (p, bytes) in [(&dll_path, LHM_DLL), (&exe_path, SENSORS_EXE)] {
            let need = match fs::metadata(p) {
                Ok(m) => m.len() != bytes.len() as u64,
                Err(_) => true,
            };
            if need {
                let _ = fs::write(p, bytes);
            }
        }
        Ok(exe_path)
    }

    pub fn read(&self) -> SensorHelperData {
        self.data.read().unwrap().clone()
    }

    pub fn stop(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
        if let Ok(mut guard) = self.child.lock() {
            if let Some((mut proc, stdin)) = guard.take() {
                drop(stdin);
                let _ = proc.kill();
                let _ = proc.wait();
            }
        }
    }
}

impl Drop for CpuTempReader {
    fn drop(&mut self) {
        self.stop();
    }
}
