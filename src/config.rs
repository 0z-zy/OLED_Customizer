use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::oled::views::clock::ClockStyle;
use crate::oled::views::hw_monitor::HwStyle;
use crate::oled::views::player::PlayerStyle;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PreviewTint {
    #[serde(alias = "Cyan")]
    White,
    IceBlue,
    Amber,
}

impl Default for PreviewTint {
    fn default() -> Self {
        Self::White
    }
}

impl PreviewTint {
    pub const ALL: [PreviewTint; 3] = [PreviewTint::White, PreviewTint::IceBlue, PreviewTint::Amber];

    pub fn label(self) -> &'static str {
        match self {
            PreviewTint::White => "Pure White",
            PreviewTint::IceBlue => "Ice Blue",
            PreviewTint::Amber => "Warm Amber",
        }
    }

    pub fn rgb(self) -> [u8; 3] {
        match self {
            PreviewTint::White => [246, 248, 252],
            PreviewTint::IceBlue => [148, 212, 255],
            PreviewTint::Amber => [255, 194, 71],
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct AppConfig {
    // Master toggles
    pub enabled: bool,
    pub output_to_oled: bool,
    pub display_clock: bool,
    pub display_player: bool,
    pub display_hw_monitor: bool,

    // Visual styles
    pub clock_style: ClockStyle,
    pub player_style: PlayerStyle,
    pub hw_style: HwStyle,
    pub preview_tint: PreviewTint,

    // Clock & Headset options
    pub use_24h: bool,
    pub display_seconds: bool,
    pub use_turkish_days: bool,
    pub headset_hid_sync_enabled: bool,
    pub show_headset_battery: bool,
    pub show_battery_percent: bool,

    // Hardware options
    pub hw_polling_ms: u64,
    pub show_game_fps: bool,
    pub selected_gpu: String,

    // Hotkeys
    pub hotkey_monitor: String,
    pub hotkey_mute: String,
    pub hotkey_mute_2: String,
    pub hotkey_calculator: String,

    // Layout
    pub scrollbar_padding: i32,
    pub text_padding_left: i32,

    // Lighting & Sync
    pub rgb_enabled: bool,
    pub rgb_color: [u8; 3],
    pub auto_launch_gg: bool,
    pub smtc_broadcast_enabled: bool,
    pub smtc_broadcast_port: u16,
    pub signalrgb_push_enabled: bool,
    pub signalrgb_push_port: u16,
    pub signalrgb_push_sender: String,
    pub signalrgb_push_include_title: bool,

    // System & Diagnostics
    pub debug_enabled: bool,
    pub start_minimized: bool,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            output_to_oled: true,
            display_clock: true,
            display_player: true,
            display_hw_monitor: false,
            clock_style: ClockStyle::CleanDigital,
            player_style: PlayerStyle::ModernCard,
            hw_style: HwStyle::ThreeColumn,
            preview_tint: PreviewTint::White,
            use_24h: true,
            display_seconds: true,
            use_turkish_days: false,
            headset_hid_sync_enabled: false,
            show_headset_battery: false,
            show_battery_percent: false,
            hw_polling_ms: 1000,
            show_game_fps: true,
            selected_gpu: "Auto".to_string(),
            hotkey_monitor: "Key.insert".to_string(),
            hotkey_mute: "Key.pause".to_string(),
            hotkey_mute_2: String::new(),
            hotkey_calculator: "Key.insert".to_string(),
            scrollbar_padding: 2,
            text_padding_left: 30,
            rgb_enabled: false,
            rgb_color: [0, 212, 170],
            auto_launch_gg: false,
            smtc_broadcast_enabled: false,
            smtc_broadcast_port: 1231,
            signalrgb_push_enabled: false,
            signalrgb_push_port: 16034,
            signalrgb_push_sender: "OLED Customizer".to_string(),
            signalrgb_push_include_title: false,
            debug_enabled: false,
            start_minimized: false,
        }
    }
}

pub fn app_data_dir() -> PathBuf {
    let base = std::env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."));
    base.join("OLED Customizer")
}

pub fn config_path() -> PathBuf {
    app_data_dir().join("settings.json")
}

impl AppConfig {
    pub fn load() -> Self {
        let p = config_path();
        if let Ok(raw) = fs::read_to_string(&p) {
            if let Ok(cfg) = serde_json::from_str::<AppConfig>(&raw) {
                return cfg;
            }
        }

        // Seamless migration from earlier v2 prototype config if present
        let p_prev = app_data_dir().join("config_v2.json");
        if let Ok(raw_prev) = fs::read_to_string(&p_prev) {
            if let Ok(cfg) = serde_json::from_str::<AppConfig>(&raw_prev) {
                let _ = cfg.save();
                return cfg;
            }
        }

        // First run: pre-fill compatible preferences read-only from v1 config.json
        let mut cfg = AppConfig::default();
        let p1 = app_data_dir().join("config.json");
        if let Ok(raw1) = fs::read_to_string(&p1) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw1) {
                if let Some(b) = v.get("display_seconds").and_then(|x| x.as_bool()) {
                    cfg.display_seconds = b;
                }
                if let Some(b) = v.get("use_turkish_days").and_then(|x| x.as_bool()) {
                    cfg.use_turkish_days = b;
                }
                if let Some(df) = v.get("date_format").and_then(|x| x.as_i64()) {
                    cfg.use_24h = df == 24;
                }
                if let Some(b) = v.get("display_timer").and_then(|x| x.as_bool()) {
                    cfg.display_clock = b;
                }
                if let Some(b) = v.get("display_player").and_then(|x| x.as_bool()) {
                    cfg.display_player = b;
                }
                if let Some(b) = v.get("display_hw_monitor").and_then(|x| x.as_bool()) {
                    cfg.display_hw_monitor = b;
                }
                if let Some(s) = v.get("hotkey_monitor").and_then(|x| x.as_str()) {
                    cfg.hotkey_monitor = s.to_string();
                }
                if let Some(s) = v.get("hotkey_mute").and_then(|x| x.as_str()) {
                    cfg.hotkey_mute = s.to_string();
                }
                if let Some(s) = v.get("hotkey_mute_2").and_then(|x| x.as_str()) {
                    cfg.hotkey_mute_2 = s.to_string();
                }
                if let Some(s) = v.get("hotkey_calculator").and_then(|x| x.as_str()) {
                    cfg.hotkey_calculator = s.to_string();
                }
                if let Some(b) = v.get("rgb_enabled").and_then(|x| x.as_bool()) {
                    cfg.rgb_enabled = b;
                }
                if let Some(arr) = v.get("rgb_color").and_then(|x| x.as_array()) {
                    if arr.len() == 3 {
                        cfg.rgb_color = [
                            arr[0].as_u64().unwrap_or(0) as u8,
                            arr[1].as_u64().unwrap_or(212) as u8,
                            arr[2].as_u64().unwrap_or(170) as u8,
                        ];
                    }
                }
                if let Some(n) = v.get("hw_polling_interval").and_then(|x| x.as_u64()) {
                    cfg.hw_polling_ms = n.clamp(250, 10000);
                }
                if let Some(b) = v.get("show_game_fps").and_then(|x| x.as_bool()) {
                    cfg.show_game_fps = b;
                }
                if let Some(b) = v.get("headset_hid_sync_enabled").and_then(|x| x.as_bool()) {
                    cfg.headset_hid_sync_enabled = b;
                }
                if let Some(b) = v.get("show_headset_battery").and_then(|x| x.as_bool()) {
                    cfg.show_headset_battery = b;
                }
                if let Some(b) = v.get("show_battery_percent").and_then(|x| x.as_bool()) {
                    cfg.show_battery_percent = b;
                }
                if let Some(b) = v.get("auto_launch_gg").and_then(|x| x.as_bool()) {
                    cfg.auto_launch_gg = b;
                }
                if let Some(b) = v.get("smtc_broadcast_enabled").and_then(|x| x.as_bool()) {
                    cfg.smtc_broadcast_enabled = b;
                }
                if let Some(n) = v.get("smtc_broadcast_port").and_then(|x| x.as_u64()) {
                    cfg.smtc_broadcast_port = n as u16;
                }
                if let Some(b) = v.get("signalrgb_push_enabled").and_then(|x| x.as_bool()) {
                    cfg.signalrgb_push_enabled = b;
                }
                if let Some(n) = v.get("signalrgb_push_port").and_then(|x| x.as_u64()) {
                    cfg.signalrgb_push_port = n as u16;
                }
                if let Some(s) = v.get("signalrgb_push_sender").and_then(|x| x.as_str()) {
                    cfg.signalrgb_push_sender = s.to_string();
                }
                if let Some(b) = v
                    .get("signalrgb_push_include_title")
                    .and_then(|x| x.as_bool())
                {
                    cfg.signalrgb_push_include_title = b;
                }
            }
        }
        let _ = cfg.save();
        cfg
    }

    pub fn save(&self) -> Result<(), String> {
        let dir = app_data_dir();
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let body = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;
        fs::write(config_path(), body).map_err(|e| e.to_string())
    }
}
