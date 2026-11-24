use std::fs;
use std::path::PathBuf;
use std::time::{Duration, Instant};

use serde_json::json;

const GAME: &str = "OLED_CUSTOMIZER_V3";
const GAME_DISPLAY_NAME: &str = "OLED Customizer";
const AUTHOR: &str = "0z-zy";
const EVENT: &str = "UPDATE";

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum GgStatus {
    Connected,
    WaitingForGg,
    ErrorBackoff,
    Paused,
}

impl GgStatus {
    pub fn label(&self) -> &'static str {
        match self {
            GgStatus::Connected => "GG Connected",
            GgStatus::WaitingForGg => "Waiting for GG",
            GgStatus::ErrorBackoff => "Reconnecting...",
            GgStatus::Paused => "OLED Paused",
        }
    }
}

pub struct SteelSeriesClient {
    agent: ureq::Agent,
    address: Option<String>,
    consecutive_errors: u32,
    backoff_until: Option<Instant>,
    pub status: GgStatus,
}

impl SteelSeriesClient {
    pub fn new() -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout_connect(Duration::from_millis(400))
            .timeout_read(Duration::from_millis(800))
            .build();
        let mut client = Self {
            agent,
            address: None,
            consecutive_errors: 0,
            backoff_until: None,
            status: GgStatus::WaitingForGg,
        };
        let _ = client.try_connect();
        client
    }

    pub fn coreprops_paths() -> Vec<PathBuf> {
        let pd = std::env::var("PROGRAMDATA").unwrap_or_else(|_| r"C:\ProgramData".to_string());
        vec![
            PathBuf::from(&pd)
                .join("SteelSeries")
                .join("SteelSeries Engine 3")
                .join("coreProps.json"),
            PathBuf::from(&pd)
                .join("SteelSeries")
                .join("SteelSeries GG")
                .join("coreProps.json"),
        ]
    }

    pub fn coreprops_exists() -> bool {
        Self::coreprops_paths().iter().any(|p| p.exists())
    }

    pub fn try_connect(&mut self) -> bool {
        for p in Self::coreprops_paths() {
            if let Ok(raw) = fs::read_to_string(&p) {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&raw) {
                    if let Some(addr) = val.get("address").and_then(|v| v.as_str()) {
                        let base = format!("http://{}", addr);
                        self.address = Some(base);
                        if self.register_and_bind() {
                            self.consecutive_errors = 0;
                            self.backoff_until = None;
                            self.status = GgStatus::Connected;
                            log::info!("Connected to SteelSeries GameSense at http://{}", addr);
                            return true;
                        }
                    }
                }
            }
        }
        self.address = None;
        self.status = GgStatus::WaitingForGg;
        false
    }

    fn register_and_bind(&self) -> bool {
        let _ = self.post_json("/remove_game", json!({ "game": GAME }));
        if !self.post_json(
            "/game_metadata",
            json!({
                "game": GAME,
                "game_display_name": GAME_DISPLAY_NAME,
                "developer": AUTHOR,
                "deinitialize_timer_length_ms": 60000
            }),
        ) {
            return false;
        }
        let dummy = vec![0u8; 640];
        self.post_json(
            "/bind_game_event",
            json!({
                "game": GAME,
                "event": EVENT,
                "value_optional": true,
                "handlers": [{
                    "device-type": "screened-128x40",
                    "mode": "screen",
                    "datas": [{
                        "has-text": false,
                        "image-data": dummy
                    }]
                }]
            }),
        )
    }

    fn post_json(&self, endpoint: &str, body: serde_json::Value) -> bool {
        let Some(ref base) = self.address else {
            return false;
        };
        let url = format!("{}{}", base, endpoint);
        match self.agent.post(&url).send_json(body) {
            Ok(resp) => resp.status() == 200,
            Err(_) => false,
        }
    }

    pub fn send_frame(&mut self, frame: &[u8; 640]) -> bool {
        if let Some(until) = self.backoff_until {
            if Instant::now() < until {
                return false;
            }
        }
        if self.address.is_none() && !self.try_connect() {
            self.backoff_until = Some(Instant::now() + Duration::from_secs(3));
            return false;
        }

        let ok = self.post_json(
            "/game_event",
            json!({
                "game": GAME,
                "event": EVENT,
                "data": {
                    "frame": {
                        "image-data-128x40": frame.as_slice()
                    }
                }
            }),
        );

        if ok {
            self.consecutive_errors = 0;
            self.backoff_until = None;
            self.status = GgStatus::Connected;
            true
        } else {
            self.consecutive_errors += 1;
            if self.consecutive_errors >= 10 {
                self.consecutive_errors = 0;
                self.address = None;
                self.status = GgStatus::ErrorBackoff;
                self.backoff_until = Some(Instant::now() + Duration::from_secs(5));
            } else if self.consecutive_errors >= 4 {
                self.status = GgStatus::ErrorBackoff;
                self.backoff_until = Some(Instant::now() + Duration::from_secs(2));
            }
            false
        }
    }

    pub fn send_rgb(&self, r: u8, g: u8, b: u8) {
        if self.address.is_none() {
            return;
        }
        let mut keys = Vec::with_capacity(450);
        for _ in 0..150 {
            keys.push(r);
            keys.push(g);
            keys.push(b);
        }
        let _ = self.post_json(
            "/game_event",
            json!({
                "game": GAME,
                "event": EVENT,
                "data": {
                    "value": 100,
                    "frame": { "rgb-per-key": keys }
                }
            }),
        );
    }

    pub fn heartbeat(&self) {
        if self.address.is_some() {
            let _ = self.post_json("/game_heartbeat", json!({ "game": GAME }));
        }
    }
}
