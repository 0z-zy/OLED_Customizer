pub mod theme;
pub mod tray;
pub mod vector_icons;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, RwLock};
use std::thread;
use std::time::{Duration, Instant};

use eframe::egui::{
    self, vec2, Color32, ColorImage, CornerRadius, Margin, RichText, Stroke, TextureHandle,
    TextureOptions,
};

use crate::config::{app_data_dir, AppConfig, PreviewTint};
use crate::ipc::{decode_hex_640, IpcClient, UiStateSnapshot};
use crate::oled::canvas::{Canvas128x40, OLED_HEIGHT, OLED_WIDTH};
use crate::oled::views::{clock::ClockStyle, hw_monitor::HwStyle, player::PlayerStyle};

use theme::*;
use vector_icons::{paint_vector_icon, IconKind};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NavTab {
    Styles,
    ClockDisplay,
    Hardware,
    Hotkeys,
    LightingSync,
    LogsSystem,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CaptureField {
    Monitor,
    Mute,
    Mute2,
    Calc,
}

enum UiCmd {
    PushConfig(AppConfig),
    SetPreview(String),
    SetStartup(bool),
    Elevate(String),
}

pub struct OledApp {
    state: Arc<RwLock<UiStateSnapshot>>,
    draft: AppConfig,
    cmd_tx: Sender<UiCmd>,
    stop_flag: Arc<AtomicBool>,
    tab: NavTab,
    oled_tex: Option<TextureHandle>,
    capturing: Option<CaptureField>,
    save_toast_until: Option<Instant>,
    dirty: bool,
}

impl OledApp {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        client: IpcClient,
        initial: UiStateSnapshot,
    ) -> Self {
        apply_modern_theme(&cc.egui_ctx);
        let draft = initial.config.clone();
        let state = Arc::new(RwLock::new(initial));
        let stop_flag = Arc::new(AtomicBool::new(false));
        let (cmd_tx, cmd_rx) = mpsc::channel::<UiCmd>();

        // Background poller for live 128x40 OLED & telemetry
        let state_p = state.clone();
        let stop_p = stop_flag.clone();
        let client_p = client.clone();
        let ctx_p = cc.egui_ctx.clone();
        thread::Builder::new()
            .name("UI-State-Poll".to_string())
            .spawn(move || {
                while !stop_p.load(Ordering::Relaxed) {
                    if let Some(snap) = client_p.get_state() {
                        *state_p.write().unwrap() = snap;
                        ctx_p.request_repaint();
                    }
                    thread::sleep(Duration::from_millis(65));
                }
            })
            .ok();

        // Background command sender so UI clicks never stall
        let stop_c = stop_flag.clone();
        thread::Builder::new()
            .name("UI-Cmd-Sender".to_string())
            .spawn(move || {
                while !stop_c.load(Ordering::Relaxed) {
                    match cmd_rx.recv_timeout(Duration::from_millis(100)) {
                        Ok(UiCmd::PushConfig(cfg)) => client.push_config(&cfg),
                        Ok(UiCmd::SetPreview(t)) => client.set_preview(&t),
                        Ok(UiCmd::SetStartup(en)) => client.set_startup(en),
                        Ok(UiCmd::Elevate(args)) => client.elevate(&args),
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                        Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    }
                }
            })
            .ok();

        Self {
            state,
            draft,
            cmd_tx,
            stop_flag,
            tab: NavTab::Styles,
            oled_tex: None,
            capturing: None,
            save_toast_until: None,
            dirty: false,
        }
    }

    fn push_draft(&mut self) {
        self.dirty = true;
        let _ = self.cmd_tx.send(UiCmd::PushConfig(self.draft.clone()));
    }

    fn handle_hotkey_capture(&mut self, ctx: &egui::Context) {
        let Some(field) = self.capturing else {
            return;
        };
        let events = ctx.input(|i| i.events.clone());
        for ev in events {
            if let egui::Event::Key {
                key,
                pressed: true,
                ..
            } = ev
            {
                if key == egui::Key::Escape {
                    self.capturing = None;
                    return;
                }
                if let Some(mapped) = egui_key_to_pref(key) {
                    match field {
                        CaptureField::Monitor => self.draft.hotkey_monitor = mapped,
                        CaptureField::Mute => self.draft.hotkey_mute = mapped,
                        CaptureField::Mute2 => self.draft.hotkey_mute_2 = mapped,
                        CaptureField::Calc => self.draft.hotkey_calculator = mapped,
                    }
                    self.capturing = None;
                    self.push_draft();
                    return;
                }
            }
        }
    }
}

impl Drop for OledApp {
    fn drop(&mut self) {
        // Restore LiveAuto on keyboard when closing Settings window
        let _ = self.cmd_tx.send(UiCmd::SetPreview("LiveAuto".to_string()));
        self.stop_flag.store(true, Ordering::Relaxed);
    }
}

impl eframe::App for OledApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.handle_hotkey_capture(ctx);

        let snap = self.state.read().unwrap().clone();
        if !self.dirty {
            self.draft = snap.config.clone();
        }

        // Update 128x40 live texture
        let mut canvas = Canvas128x40::new();
        canvas.data = decode_hex_640(&snap.pixels_hex);
        let rgba = canvas.to_rgba_preview(self.draft.preview_tint.rgb());
        let color_img =
            ColorImage::from_rgba_unmultiplied([OLED_WIDTH as usize, OLED_HEIGHT as usize], &rgba);
        match self.oled_tex {
            Some(ref mut tex) => tex.set(color_img, TextureOptions::NEAREST),
            None => {
                self.oled_tex =
                    Some(ctx.load_texture("oled_live", color_img, TextureOptions::NEAREST));
            }
        }

        // === LEFT SIDEBAR ===
        egui::SidePanel::left("sidebar")
            .resizable(false)
            .exact_width(198.0)
            .frame(
                egui::Frame::new()
                    .fill(BG_SIDEBAR)
                    .stroke(Stroke::new(1.0_f32, BORDER))
                    .inner_margin(Margin::same(14)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    let (icon_rect, _) =
                        ui.allocate_exact_size(vec2(26.0, 20.0), egui::Sense::hover());
                    paint_vector_icon(ui, icon_rect, IconKind::BrandOled, ACCENT);
                    ui.vertical(|ui| {
                        ui.label(
                            RichText::new("OLED Customizer")
                                .size(14.0)
                                .strong()
                                .color(TEXT_MAIN),
                        );
                        egui::Frame::new()
                            .fill(BG_ELEVATED)
                            .stroke(Stroke::new(1.0_f32, BORDER))
                            .corner_radius(CornerRadius::same(4))
                            .inner_margin(Margin::symmetric(6, 1))
                            .show(ui, |ui| {
                                ui.label(
                                    RichText::new(concat!("v", env!("CARGO_PKG_VERSION")))
                                        .size(9.5)
                                        .strong()
                                        .color(TEXT_DIM),
                                );
                            });
                    });
                });

                ui.add_space(16.0);

                let nav_items = [
                    (NavTab::Styles, "Styles & Preview", IconKind::Styles),
                    (NavTab::ClockDisplay, "Clock & Display", IconKind::Clock),
                    (NavTab::Hardware, "Hardware", IconKind::Cpu),
                    (NavTab::Hotkeys, "Hotkeys", IconKind::Keyboard),
                    (NavTab::LightingSync, "Lighting & Sync", IconKind::Sparkles),
                    (NavTab::LogsSystem, "Logs & System", IconKind::Logs),
                ];

                for (tab, label, icon) in nav_items {
                    let selected = self.tab == tab;
                    let fill = if selected {
                        BG_ELEVATED
                    } else {
                        Color32::TRANSPARENT
                    };
                    let stroke = if selected {
                        Stroke::new(1.0_f32, BORDER)
                    } else {
                        Stroke::NONE
                    };
                    let resp = egui::Frame::new()
                        .fill(fill)
                        .stroke(stroke)
                        .corner_radius(CornerRadius::same(8))
                        .inner_margin(Margin::symmetric(10, 8))
                        .show(ui, |ui| {
                            ui.set_width(ui.available_width());
                            ui.horizontal(|ui| {
                                let (ir, _) =
                                    ui.allocate_exact_size(vec2(16.0, 16.0), egui::Sense::hover());
                                paint_vector_icon(
                                    ui,
                                    ir,
                                    icon,
                                    if selected { ACCENT } else { TEXT_DIM },
                                );
                                ui.add_space(4.0);
                                ui.label(
                                    RichText::new(label)
                                        .size(12.5)
                                        .color(if selected { TEXT_MAIN } else { TEXT_DIM }),
                                );
                            });
                        })
                        .response
                        .interact(egui::Sense::click());
                    if resp.clicked() {
                        self.tab = tab;
                    }
                }

                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    let saved_recently = self
                        .save_toast_until
                        .map(|t| Instant::now() < t)
                        .unwrap_or(false);
                    let btn_txt = if saved_recently { "Saved" } else { "Save Settings" };
                    let save_btn = egui::Button::new(
                        RichText::new(btn_txt)
                            .size(13.0)
                            .strong()
                            .color(BG_ROOT),
                    )
                    .fill(if saved_recently { ACCENT_SOFT } else { ACCENT })
                    .corner_radius(CornerRadius::same(8))
                    .min_size(vec2(ui.available_width(), 34.0));
                    if ui.add(save_btn).clicked() {
                        self.push_draft();
                        self.dirty = false;
                        self.save_toast_until = Some(Instant::now() + Duration::from_secs(2));
                    }

                    ui.add_space(10.0);

                    card(ui, |ui| {
                        ui.set_width(ui.available_width());
                        let dot_col = if snap.gg_status == "GG Connected" {
                            STATUS_OK
                        } else if snap.gg_status.contains("Error") || snap.gg_status.contains("Reconnect") {
                            DANGER
                        } else {
                            STATUS_WARN
                        };
                        ui.horizontal(|ui| {
                            let (dr, _) =
                                ui.allocate_exact_size(vec2(8.0, 8.0), egui::Sense::hover());
                            ui.painter().circle_filled(dr.center(), 3.5, dot_col);
                            ui.label(RichText::new(&snap.gg_status).size(11.5).color(TEXT_MAIN));
                        });
                        ui.label(
                            RichText::new(format!(
                                "Daemon: {:.1} MB  •  {:.2} ms/f",
                                snap.daemon_ram_mb,
                                snap.render_us as f32 / 1000.0
                            ))
                            .size(10.5)
                            .color(TEXT_DIM),
                        );
                    });
                });
            });

        // === MAIN CONTENT ===
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(BG_ROOT)
                    .inner_margin(Margin::same(18)),
            )
            .show(ctx, |ui| {
                if !snap.is_admin {
                    egui::Frame::new()
                        .fill(BG_CARD)
                        .stroke(Stroke::new(1.0_f32, BORDER_STRONG))
                        .corner_radius(CornerRadius::same(8))
                        .inner_margin(Margin::symmetric(12, 8))
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                let (dr, _) =
                                    ui.allocate_exact_size(vec2(8.0, 8.0), egui::Sense::hover());
                                ui.painter().circle_filled(dr.center(), 3.5, STATUS_WARN);
                                let banner_msg = if snap.startup_enabled {
                                    "Running without Admin (Task Scheduler is active for Windows startup)"
                                } else {
                                    "Admin required for CPU Temp & Game FPS"
                                };
                                ui.label(
                                    RichText::new(banner_msg)
                                        .size(12.0)
                                        .strong()
                                        .color(TEXT_MAIN),
                                );
                                ui.with_layout(
                                    egui::Layout::right_to_left(egui::Align::Center),
                                    |ui| {
                                        if snap.startup_enabled {
                                            let relaunch_btn = egui::Button::new(
                                                RichText::new("Relaunch as Admin")
                                                    .size(11.5)
                                                    .strong()
                                                    .color(BG_ROOT),
                                            )
                                            .fill(ACCENT)
                                            .corner_radius(CornerRadius::same(6));
                                            if ui.add(relaunch_btn).clicked() {
                                                let _ = self.cmd_tx.send(UiCmd::Elevate("--elevated".into()));
                                            }
                                        } else {
                                            let admin_btn = egui::Button::new(
                                                RichText::new("Enable Admin via Task Scheduler")
                                                    .size(11.5)
                                                    .strong()
                                                    .color(BG_ROOT),
                                            )
                                            .fill(ACCENT)
                                            .corner_radius(CornerRadius::same(6));
                                            if ui.add(admin_btn).clicked() {
                                                let _ = self.cmd_tx.send(UiCmd::Elevate("--setup-admin-task".into()));
                                            }
                                            if ui.button("Relaunch as Admin").clicked() {
                                                let _ = self.cmd_tx.send(UiCmd::Elevate("--elevated".into()));
                                            }
                                        }
                                    },
                                );
                            });
                        });
                    ui.add_space(10.0);
                }

                // Pinned Hero: Live 128x40 OLED Simulator
                card(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(
                            RichText::new("LIVE 128×40 OLED")
                                .size(11.0)
                                .strong()
                                .color(ACCENT),
                        );
                        ui.label(
                            RichText::new(format!("•  {}", snap.active_view))
                                .size(11.0)
                                .color(TEXT_DIM),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if toggle_switch(ui, &mut self.draft.output_to_oled).changed() {
                                self.push_draft();
                            }
                            ui.label(
                                RichText::new("Stream to Keyboard")
                                    .size(11.5)
                                    .color(TEXT_DIM),
                            );
                        });
                    });
                    ui.add_space(8.0);

                    ui.vertical_centered(|ui| {
                        if let Some(ref tex) = self.oled_tex {
                            egui::Frame::new()
                                .fill(Color32::from_rgb(4, 4, 6))
                                .stroke(Stroke::new(1.5_f32, BORDER_STRONG))
                                .corner_radius(CornerRadius::same(8))
                                .inner_margin(Margin::same(8))
                                .show(ui, |ui| {
                                    ui.image((tex.id(), vec2(448.0, 140.0)));
                                });
                        }
                    });

                    ui.add_space(8.0);
                    ui.horizontal_wrapped(|ui| {
                        let targets = [
                            ("LiveAuto", "Live Auto"),
                            ("Clock", "Clock"),
                            ("Player", "Media Player"),
                            ("HwMonitor", "HW Monitor"),
                            ("Volume", "Volume"),
                            ("Calculator", "Calculator"),
                        ];
                        for (t, lbl) in targets {
                            if style_chip(ui, lbl, snap.preview_target == t) {
                                let _ = self.cmd_tx.send(UiCmd::SetPreview(t.to_string()));
                            }
                        }
                    });
                });

                ui.add_space(12.0);

                // Tab Body
                egui::ScrollArea::vertical().show(ui, |ui| match self.tab {
                    NavTab::Styles => {
                        card(ui, |ui| {
                            section_title(ui, "Clock Style", "Select the active 128x40 clock face");
                            ui.horizontal_wrapped(|ui| {
                                for st in ClockStyle::ALL {
                                    if style_chip(ui, st.label(), self.draft.clock_style == st) {
                                        self.draft.clock_style = st;
                                        self.push_draft();
                                        let _ = self.cmd_tx.send(UiCmd::SetPreview("Clock".into()));
                                    }
                                }
                            });
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Media Player Style",
                                "Layout used when Spotify, YouTube, or Windows media is playing",
                            );
                            ui.horizontal_wrapped(|ui| {
                                for st in PlayerStyle::ALL {
                                    if style_chip(ui, st.label(), self.draft.player_style == st) {
                                        self.draft.player_style = st;
                                        self.push_draft();
                                        let _ = self.cmd_tx.send(UiCmd::SetPreview("Player".into()));
                                    }
                                }
                            });
                            if snap.media_active {
                                ui.add_space(4.0);
                                ui.label(
                                    RichText::new(format!(
                                        "Now Playing: {} — {}",
                                        snap.media_artist, snap.media_title
                                    ))
                                    .size(11.0)
                                    .color(ACCENT_SOFT),
                                );
                            }
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Hardware Monitor Style",
                                "Layout for CPU, GPU, RAM & FPS",
                            );
                            ui.horizontal_wrapped(|ui| {
                                for st in HwStyle::ALL {
                                    if style_chip(ui, st.label(), self.draft.hw_style == st) {
                                        self.draft.hw_style = st;
                                        self.push_draft();
                                        let _ = self.cmd_tx.send(UiCmd::SetPreview("HwMonitor".into()));
                                    }
                                }
                            });
                        });
                    }

                    NavTab::ClockDisplay => {
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Display Features",
                                "Toggle what appears on your keyboard screen",
                            );
                            if toggle_row(
                                ui,
                                "Enable OLED Customizer",
                                "Master switch for OLED output",
                                &mut self.draft.enabled,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Enable Clock",
                                "Shown when no media is playing",
                                &mut self.draft.display_clock,
                            ) {
                                if self.draft.display_clock {
                                    self.draft.display_hw_monitor = false;
                                }
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Enable Media Player",
                                "Auto-switch when Spotify/YouTube plays",
                                &mut self.draft.display_player,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "24-Hour Clock",
                                "Off = 12-hour AM/PM",
                                &mut self.draft.use_24h,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Show Seconds",
                                "Live seconds tick",
                                &mut self.draft.display_seconds,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Turkish Day & Month Names",
                                "Pzt / Sal / Car...",
                                &mut self.draft.use_turkish_days,
                            ) {
                                self.push_draft();
                            }
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Headset Battery & HID Sync (HyperX / NGENUITY)",
                                "Direct USB HID battery & mute sync — works even without NGENUITY running",
                            );
                            ui.label(
                                RichText::new(format!("Status: {}", snap.hid_status))
                                    .size(11.5)
                                    .color(ACCENT_SOFT),
                            );
                            ui.add_space(4.0);
                            if toggle_row(
                                ui,
                                "Enable Headset HID Sync",
                                "Syncs physical headset mute button & reads wireless battery",
                                &mut self.draft.headset_hid_sync_enabled,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Show Headset Battery on Clock",
                                "Draws battery indicator in the top-right of the clock screen",
                                &mut self.draft.show_headset_battery,
                            ) {
                                if self.draft.show_headset_battery {
                                    self.draft.headset_hid_sync_enabled = true;
                                }
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Show Battery Percentage Number",
                                "Displays numeric % underneath the battery icon",
                                &mut self.draft.show_battery_percent,
                            ) {
                                self.push_draft();
                            }
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Simulator Tint",
                                "Preview phosphor color (your physical keyboard OLED is monochrome white)",
                            );
                            ui.horizontal_wrapped(|ui| {
                                for t in PreviewTint::ALL {
                                    if style_chip(ui, t.label(), self.draft.preview_tint == t) {
                                        self.draft.preview_tint = t;
                                        self.push_draft();
                                    }
                                }
                            });
                        });
                    }

                    NavTab::Hardware => {
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Live Telemetry",
                                "Native NVML + embedded LibreHardwareMonitor + PresentMon FPS",
                            );
                            let fps_text = if !self.draft.show_game_fps {
                                "Off".to_string()
                            } else if snap.hw_fps_status == "Needs Admin" {
                                "Needs Admin".to_string()
                            } else if let Some(f) = snap.hw_fps {
                                if f > 0 {
                                    format!("{} FPS", f)
                                } else {
                                    "Idle".to_string()
                                }
                            } else {
                                snap.hw_fps_status.clone()
                            };

                            ui.label(
                                RichText::new(format!(
                                    "CPU: {}% ({})  |  GPU ({}): {} ({})  |  RAM: {:.1}/{:.0} GB ({}%)  |  FPS: {}",
                                    snap.hw_cpu_load,
                                    snap.hw_cpu_temp
                                        .map(|t| format!("{}°C", t))
                                        .unwrap_or_else(|| if snap.is_admin { "--".into() } else { "Needs Admin".into() }),
                                    snap.hw_gpu_name,
                                    snap.hw_gpu_temp
                                        .map(|t| format!("{}°C", t))
                                        .unwrap_or_else(|| "--".into()),
                                    snap.hw_gpu_load
                                        .map(|l| format!("{}%", l))
                                        .unwrap_or_else(|| "--".into()),
                                    snap.hw_ram_used,
                                    snap.hw_ram_total,
                                    snap.hw_ram_pct,
                                    fps_text,
                                ))
                                .size(12.0)
                                .color(ACCENT_SOFT),
                            );
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(ui, "Hardware Options", "");
                            if toggle_row(
                                ui,
                                "Always Show System Stats",
                                "Pins HW Monitor instead of Clock",
                                &mut self.draft.display_hw_monitor,
                            ) {
                                if self.draft.display_hw_monitor {
                                    self.draft.display_clock = false;
                                }
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Show Game FPS (PresentMon)",
                                "Live in-game FPS on HW Monitor (requires Administrator)",
                                &mut self.draft.show_game_fps,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            ui.horizontal(|ui| {
                                ui.label(
                                    RichText::new("Polling Interval")
                                        .size(13.0)
                                        .color(TEXT_MAIN),
                                );
                                ui.with_layout(
                                    egui::Layout::right_to_left(egui::Align::Center),
                                    |ui| {
                                        for (ms, lbl) in [
                                            (500, "500ms"),
                                            (1000, "1s"),
                                            (2000, "2s"),
                                            (5000, "5s"),
                                        ] {
                                            if style_chip(ui, lbl, self.draft.hw_polling_ms == ms) {
                                                self.draft.hw_polling_ms = ms;
                                                self.push_draft();
                                            }
                                        }
                                    },
                                );
                            });
                        });
                    }

                    NavTab::Hotkeys => {
                        card(ui, |ui| {
                            section_title(ui, "Global Hotkeys", "Work even inside fullscreen games");
                            let rows = [
                                (
                                    CaptureField::Monitor,
                                    "Peek System Stats",
                                    self.draft.hotkey_monitor.clone(),
                                ),
                                (
                                    CaptureField::Mute,
                                    "Mute Mic (Primary)",
                                    self.draft.hotkey_mute.clone(),
                                ),
                                (
                                    CaptureField::Mute2,
                                    "Mute Mic (Secondary)",
                                    self.draft.hotkey_mute_2.clone(),
                                ),
                                (
                                    CaptureField::Calc,
                                    "Calculator (Ctrl + Key)",
                                    self.draft.hotkey_calculator.clone(),
                                ),
                            ];
                            for (field, label, val) in rows {
                                ui.horizontal(|ui| {
                                    ui.label(RichText::new(label).size(13.0).color(TEXT_MAIN));
                                    ui.with_layout(
                                        egui::Layout::right_to_left(egui::Align::Center),
                                        |ui| {
                                            if ui.button("Clear").clicked() {
                                                match field {
                                                    CaptureField::Monitor => {
                                                        self.draft.hotkey_monitor.clear()
                                                    }
                                                    CaptureField::Mute => {
                                                        self.draft.hotkey_mute.clear()
                                                    }
                                                    CaptureField::Mute2 => {
                                                        self.draft.hotkey_mute_2.clear()
                                                    }
                                                    CaptureField::Calc => {
                                                        self.draft.hotkey_calculator.clear()
                                                    }
                                                }
                                                self.push_draft();
                                            }
                                            if ui.button("M5").clicked() {
                                                let v = "Key.mouse_5".to_string();
                                                match field {
                                                    CaptureField::Monitor => {
                                                        self.draft.hotkey_monitor = v
                                                    }
                                                    CaptureField::Mute => self.draft.hotkey_mute = v,
                                                    CaptureField::Mute2 => {
                                                        self.draft.hotkey_mute_2 = v
                                                    }
                                                    CaptureField::Calc => {
                                                        self.draft.hotkey_calculator = v
                                                    }
                                                }
                                                self.push_draft();
                                            }
                                            if ui.button("M4").clicked() {
                                                let v = "Key.mouse_4".to_string();
                                                match field {
                                                    CaptureField::Monitor => {
                                                        self.draft.hotkey_monitor = v
                                                    }
                                                    CaptureField::Mute => self.draft.hotkey_mute = v,
                                                    CaptureField::Mute2 => {
                                                        self.draft.hotkey_mute_2 = v
                                                    }
                                                    CaptureField::Calc => {
                                                        self.draft.hotkey_calculator = v
                                                    }
                                                }
                                                self.push_draft();
                                            }
                                            let is_cap = self.capturing == Some(field);
                                            let btn_lbl = if is_cap { "Press key..." } else { "Set" };
                                            if ui.button(btn_lbl).clicked() {
                                                self.capturing = Some(field);
                                            }
                                            ui.label(
                                                RichText::new(if val.is_empty() {
                                                    "None"
                                                } else {
                                                    &val
                                                })
                                                .size(12.0)
                                                .color(TEXT_DIM),
                                            );
                                        },
                                    );
                                });
                                ui.separator();
                            }
                        });
                    }

                    NavTab::LightingSync => {
                        card(ui, |ui| {
                            section_title(
                                ui,
                                "Keyboard RGB & SignalRGB Sync",
                                "Localhost-only integrations",
                            );
                            if toggle_row(
                                ui,
                                "Match Keyboard RGB",
                                "Sets SteelSeries per-key RGB color",
                                &mut self.draft.rgb_enabled,
                            ) {
                                self.push_draft();
                            }
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("RGB Color").size(13.0).color(TEXT_MAIN));
                                ui.with_layout(
                                    egui::Layout::right_to_left(egui::Align::Center),
                                    |ui| {
                                        if ui
                                            .color_edit_button_srgb(&mut self.draft.rgb_color)
                                            .changed()
                                        {
                                            self.push_draft();
                                        }
                                    },
                                );
                            });
                            ui.separator();
                            if toggle_row(
                                ui,
                                "SMTC HTTP Broadcast",
                                "Serves GET /media and /cover.jpg on 127.0.0.1",
                                &mut self.draft.smtc_broadcast_enabled,
                            ) {
                                self.push_draft();
                            }
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("Broadcast Port").size(12.5).color(TEXT_DIM));
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    if ui
                                        .add(
                                            egui::DragValue::new(&mut self.draft.smtc_broadcast_port)
                                                .range(1024..=65535)
                                                .speed(1),
                                        )
                                        .changed()
                                    {
                                        self.push_draft();
                                    }
                                });
                            });
                            ui.separator();
                            if toggle_row(
                                ui,
                                "SignalRGB Album Color Push",
                                "Pushes play state & 5 dominant album colors to SignalRGB",
                                &mut self.draft.signalrgb_push_enabled,
                            ) {
                                self.push_draft();
                            }
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("SignalRGB Port").size(12.5).color(TEXT_DIM));
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    if ui
                                        .add(
                                            egui::DragValue::new(&mut self.draft.signalrgb_push_port)
                                                .range(1024..=65535)
                                                .speed(1),
                                        )
                                        .changed()
                                    {
                                        self.push_draft();
                                    }
                                });
                            });
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("SignalRGB Sender").size(12.5).color(TEXT_DIM));
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    if ui
                                        .add(
                                            egui::TextEdit::singleline(&mut self.draft.signalrgb_push_sender)
                                                .desired_width(150.0),
                                        )
                                        .changed()
                                    {
                                        self.push_draft();
                                    }
                                });
                            });
                            if toggle_row(
                                ui,
                                "Include Track Title in SignalRGB Event",
                                "Sends sanitized track title (t.<title>) alongside colors",
                                &mut self.draft.signalrgb_push_include_title,
                            ) {
                                self.push_draft();
                            }
                        });
                    }

                    NavTab::LogsSystem => {
                        card(ui, |ui| {
                            section_title(ui, "Admin & Startup (Task Scheduler)", "");
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("Privilege Status:").size(12.5).color(TEXT_DIM));
                                if snap.is_admin {
                                    ui.label(RichText::new("Administrator (Active)").size(12.5).strong().color(STATUS_OK));
                                } else {
                                    ui.label(RichText::new("Standard User").size(12.5).strong().color(STATUS_WARN));
                                }
                            });
                            ui.horizontal(|ui| {
                                ui.label(RichText::new("Task Scheduler:").size(12.5).color(TEXT_DIM));
                                let st_txt = if snap.startup_enabled {
                                    "Registered ('OLED Customizer' - Runs as Admin at Logon)"
                                } else {
                                    "Not Registered"
                                };
                                ui.label(RichText::new(st_txt).size(12.5).color(TEXT_MAIN));
                            });
                            ui.add_space(6.0);
                            ui.horizontal(|ui| {
                                if !snap.startup_enabled {
                                    if ui.button("Register Admin Startup Task").clicked() {
                                        if snap.is_admin {
                                            let _ = self.cmd_tx.send(UiCmd::SetStartup(true));
                                        } else {
                                            let _ = self.cmd_tx.send(UiCmd::Elevate("--setup-admin-task".into()));
                                        }
                                    }
                                } else if ui.button("Remove Startup Task").clicked() {
                                    if snap.is_admin {
                                        let _ = self.cmd_tx.send(UiCmd::SetStartup(false));
                                    } else {
                                        let _ = self.cmd_tx.send(UiCmd::Elevate("--elevated".into()));
                                    }
                                }
                                if ui.button("Open Config & Logs Folder").clicked() {
                                    let _ = std::process::Command::new("explorer")
                                        .arg(app_data_dir())
                                        .spawn();
                                }
                            });
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Start Minimized to Tray",
                                "Starts hidden in system tray",
                                &mut self.draft.start_minimized,
                            ) {
                                self.push_draft();
                            }
                            ui.separator();
                            if toggle_row(
                                ui,
                                "Verbose Debug Logging",
                                "Writes detailed diagnostics to debug.log",
                                &mut self.draft.debug_enabled,
                            ) {
                                self.push_draft();
                            }
                        });
                        ui.add_space(10.0);
                        card(ui, |ui| {
                            section_title(ui, "Recent Logs", "");
                            let logs = snap.logs.join("\n");
                            egui::ScrollArea::vertical().max_height(150.0).show(ui, |ui| {
                                ui.add(
                                    egui::TextEdit::multiline(&mut logs.as_str())
                                        .font(egui::TextStyle::Monospace)
                                        .desired_width(f32::INFINITY),
                                );
                            });
                        });
                    }
                });
            });
    }
}

fn egui_key_to_pref(key: egui::Key) -> Option<String> {
    use egui::Key;
    let s = match key {
        Key::Insert => "Key.insert",
        Key::Delete => "Key.delete",
        Key::Home => "Key.home",
        Key::End => "Key.end",
        Key::PageUp => "Key.page_up",
        Key::PageDown => "Key.page_down",
        Key::Space => "Key.space",
        Key::Enter => "Key.enter",
        Key::Backspace => "Key.backspace",
        Key::Tab => "Key.tab",
        Key::ArrowUp => "Key.up",
        Key::ArrowDown => "Key.down",
        Key::ArrowLeft => "Key.left",
        Key::ArrowRight => "Key.right",
        Key::F1 => "Key.f1",
        Key::F2 => "Key.f2",
        Key::F3 => "Key.f3",
        Key::F4 => "Key.f4",
        Key::F5 => "Key.f5",
        Key::F6 => "Key.f6",
        Key::F7 => "Key.f7",
        Key::F8 => "Key.f8",
        Key::F9 => "Key.f9",
        Key::F10 => "Key.f10",
        Key::F11 => "Key.f11",
        Key::F12 => "Key.f12",
        _ => return None,
    };
    Some(s.to_string())
}
