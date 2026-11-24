use std::fs;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::config::{app_data_dir, AppConfig};
use crate::engine::{EngineHandle, PreviewTarget};
use crate::logging::recent_logs;
use crate::oled::views::hw_monitor::HwStats;
use crate::platform::startup::{is_running_as_admin, is_startup_enabled, relaunch_as_admin, set_startup_enabled};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UiStateSnapshot {
    pub pixels_hex: String,
    pub active_view: String,
    pub render_us: u64,
    pub gg_status: String,
    pub daemon_ram_mb: f32,
    pub is_admin: bool,
    pub startup_enabled: bool,
    pub hid_status: String,
    pub hw_cpu_load: u8,
    pub hw_cpu_temp: Option<i32>,
    pub hw_gpu_name: String,
    pub hw_gpu_temp: Option<i32>,
    pub hw_gpu_load: Option<u8>,
    pub hw_ram_used: f32,
    pub hw_ram_total: f32,
    pub hw_ram_pct: u8,
    pub hw_fps: Option<u32>,
    pub hw_fps_status: String,
    pub media_active: bool,
    pub media_title: String,
    pub media_artist: String,
    pub preview_target: String,
    pub config: AppConfig,
    pub logs: Vec<String>,
}

impl Default for UiStateSnapshot {
    fn default() -> Self {
        Self {
            pixels_hex: "0".repeat(1280),
            active_view: "CLOCK".to_string(),
            render_us: 0,
            gg_status: "Connecting...".to_string(),
            daemon_ram_mb: 0.0,
            is_admin: false,
            startup_enabled: false,
            hid_status: "Disabled".to_string(),
            hw_cpu_load: 0,
            hw_cpu_temp: None,
            hw_gpu_name: "GPU".to_string(),
            hw_gpu_temp: None,
            hw_gpu_load: None,
            hw_ram_used: 0.0,
            hw_ram_total: 0.0,
            hw_ram_pct: 0,
            hw_fps: None,
            hw_fps_status: "Off".to_string(),
            media_active: false,
            media_title: String::new(),
            media_artist: String::new(),
            preview_target: "LiveAuto".to_string(),
            config: AppConfig::default(),
            logs: Vec::new(),
        }
    }
}

pub fn ipc_port_file() -> PathBuf {
    app_data_dir().join("ipc.port")
}

pub fn read_running_port() -> Option<u16> {
    fs::read_to_string(ipc_port_file())
        .ok()
        .and_then(|s| s.trim().parse::<u16>().ok())
}

fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(HEX[(b >> 4) as usize] as char);
        s.push(HEX[(b & 0x0F) as usize] as char);
    }
    s
}

pub fn decode_hex_640(s: &str) -> [u8; 640] {
    let mut out = [0u8; 640];
    let bytes = s.as_bytes();
    for (i, slot) in out.iter_mut().enumerate() {
        let idx = i * 2;
        if idx + 1 >= bytes.len() {
            break;
        }
        let hi = hex_val(bytes[idx]);
        let lo = hex_val(bytes[idx + 1]);
        *slot = (hi << 4) | lo;
    }
    out
}

#[inline]
fn hex_val(b: u8) -> u8 {
    match b {
        b'0'..=b'9' => b - b'0',
        b'a'..=b'f' => b - b'a' + 10,
        b'A'..=b'F' => b - b'A' + 10,
        _ => 0,
    }
}

fn target_to_str(t: PreviewTarget) -> &'static str {
    match t {
        PreviewTarget::LiveAuto => "LiveAuto",
        PreviewTarget::Clock => "Clock",
        PreviewTarget::Player => "Player",
        PreviewTarget::HwMonitor => "HwMonitor",
        PreviewTarget::Volume => "Volume",
        PreviewTarget::Calculator => "Calculator",
    }
}

fn str_to_target(s: &str) -> PreviewTarget {
    match s {
        "Clock" => PreviewTarget::Clock,
        "Player" => PreviewTarget::Player,
        "HwMonitor" => PreviewTarget::HwMonitor,
        "Volume" => PreviewTarget::Volume,
        "Calculator" => PreviewTarget::Calculator,
        _ => PreviewTarget::LiveAuto,
    }
}

pub enum DaemonEvent {
    OpenUi,
    Quit,
    ConfigChanged,
}

pub fn start_ipc_server(
    engine: Arc<EngineHandle>,
    daemon_tx: std::sync::mpsc::Sender<DaemonEvent>,
    stop_flag: Arc<AtomicBool>,
) -> Option<u16> {
    let listener = TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    let _ = listener.set_nonblocking(true);

    let _ = fs::create_dir_all(app_data_dir());
    let _ = fs::write(ipc_port_file(), port.to_string());

    let is_admin = is_running_as_admin();

    thread::Builder::new()
        .name("Daemon-IPC".to_string())
        .spawn(move || {
            while !stop_flag.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        let _ = stream.set_read_timeout(Some(Duration::from_millis(300)));
                        let mut buf = [0u8; 16384];
                        if let Ok(n) = stream.read(&mut buf) {
                            let req_str = String::from_utf8_lossy(&buf[..n]);
                            let first_line = req_str.lines().next().unwrap_or("");
                            let mut parts = first_line.split_whitespace();
                            let method = parts.next().unwrap_or("GET");
                            let path = parts.next().unwrap_or("/");
                            let body = req_str
                                .split("\r\n\r\n")
                                .nth(1)
                                .unwrap_or("");

                            if method == "GET" && path == "/state" {
                                let snap = engine.snapshot.read().unwrap().clone();
                                let hw: HwStats = engine.hw_stats.read().unwrap().clone();
                                let media = engine.media_state.read().unwrap().clone();
                                let cfg = engine.config.read().unwrap().clone();
                                let tgt = *engine.preview_target.read().unwrap();
                                let logs = recent_logs();
                                let tail: Vec<String> = logs.into_iter().rev().take(80).collect::<Vec<_>>().into_iter().rev().collect();

                                let payload = UiStateSnapshot {
                                    pixels_hex: encode_hex(&snap.pixels),
                                    active_view: snap.active_view,
                                    render_us: snap.render_us,
                                    gg_status: snap.gg_status.label().to_string(),
                                    daemon_ram_mb: snap.ram_mb,
                                    is_admin,
                                    startup_enabled: is_startup_enabled(),
                                    hid_status: engine.headset_hid.status_summary(),
                                    hw_cpu_load: hw.cpu_load_pct,
                                    hw_cpu_temp: hw.cpu_temp_c,
                                    hw_gpu_name: hw.gpu_name,
                                    hw_gpu_temp: hw.gpu_temp_c,
                                    hw_gpu_load: hw.gpu_load_pct,
                                    hw_ram_used: hw.ram_used_gb,
                                    hw_ram_total: hw.ram_total_gb,
                                    hw_ram_pct: hw.ram_pct,
                                    hw_fps: hw.fps,
                                    hw_fps_status: hw.fps_status,
                                    media_active: media.active,
                                    media_title: media.title,
                                    media_artist: media.artist,
                                    preview_target: target_to_str(tgt).to_string(),
                                    config: cfg,
                                    logs: tail,
                                };
                                let json = serde_json::to_string(&payload).unwrap_or_else(|_| "{}".into());
                                let resp = format!(
                                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{}",
                                    json.len(),
                                    json
                                );
                                let _ = stream.write_all(resp.as_bytes());
                            } else if method == "POST" && path == "/config" {
                                if let Ok(new_cfg) = serde_json::from_str::<AppConfig>(body) {
                                    *engine.config.write().unwrap() = new_cfg.clone();
                                    engine.apply_config(&new_cfg);
                                    let _ = new_cfg.save();
                                    let _ = daemon_tx.send(DaemonEvent::ConfigChanged);
                                }
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                            } else if method == "POST" && path == "/preview" {
                                let t = str_to_target(body.trim());
                                *engine.preview_target.write().unwrap() = t;
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                            } else if method == "POST" && path == "/startup" {
                                if let Ok(v) = serde_json::from_str::<serde_json::Value>(body) {
                                    let en = v.get("enable").and_then(|x| x.as_bool()).unwrap_or(false);
                                    let _ = set_startup_enabled(en, true);
                                }
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                            } else if method == "POST" && path == "/open-ui" {
                                let _ = daemon_tx.send(DaemonEvent::OpenUi);
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                            } else if method == "POST" && path == "/elevate" {
                                let args = body.trim().to_string();
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                                let dtx = daemon_tx.clone();
                                thread::spawn(move || {
                                    if relaunch_as_admin(&args) {
                                        let _ = dtx.send(DaemonEvent::Quit);
                                    }
                                });
                            } else if method == "POST" && path == "/quit" {
                                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
                                let _ = daemon_tx.send(DaemonEvent::Quit);
                            } else {
                                let _ = stream.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n");
                            }
                        }
                    }
                    Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(20));
                    }
                    Err(_) => {
                        thread::sleep(Duration::from_millis(50));
                    }
                }
            }
            let _ = fs::remove_file(ipc_port_file());
        })
        .ok()?;

    Some(port)
}

#[derive(Clone)]
pub struct IpcClient {
    agent: ureq::Agent,
    base: String,
}

impl IpcClient {
    pub fn new(port: u16) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_millis(250))
            .timeout_read(Duration::from_millis(400))
            .build();
        Self {
            agent,
            base: format!("http://127.0.0.1:{}", port),
        }
    }

    pub fn get_state(&self) -> Option<UiStateSnapshot> {
        let url = format!("{}/state", self.base);
        self.agent.get(&url).call().ok()?.into_json().ok()
    }

    pub fn push_config(&self, cfg: &AppConfig) {
        let url = format!("{}/config", self.base);
        let _ = self.agent.post(&url).send_json(cfg);
    }

    pub fn set_preview(&self, target: &str) {
        let url = format!("{}/preview", self.base);
        let _ = self.agent.post(&url).send_string(target);
    }

    pub fn set_startup(&self, enable: bool) {
        let url = format!("{}/startup", self.base);
        let _ = self
            .agent
            .post(&url)
            .send_json(serde_json::json!({ "enable": enable }));
    }

    pub fn elevate(&self, args: &str) {
        let url = format!("{}/elevate", self.base);
        let _ = self.agent.post(&url).send_string(args);
    }

    pub fn wake_open_ui(port: u16) -> bool {
        let c = Self::new(port);
        let url = format!("{}/open-ui", c.base);
        c.agent.post(&url).call().is_ok()
    }
}
