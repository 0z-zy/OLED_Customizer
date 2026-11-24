use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    mpsc::Receiver,
    Arc, Mutex, RwLock,
};
use std::thread;
use std::time::{Duration, Instant};

use crate::config::AppConfig;
use crate::oled::canvas::{Canvas128x40, OLED_BYTES};
use crate::oled::views::{
    calculator::CalculatorView,
    clock::{render_clock, ClockViewOpts},
    hw_monitor::{render_hw, HwStats},
    player::{MediaSource, PlayerStyle, PlayerView, SPECTRUM_BANDS},
    volume::render_volume,
};
use crate::platform::{
    audio::{start_audio_poller, AudioCommand, AudioState},
    fps::FpsMonitor,
    hardware::{process_memory_mb, start_hw_poller},
    hid::HeadsetHid,
    hotkeys::{start_hotkey_hook, HotkeyAction, HotkeyController},
    smtc::{start_smtc_poller, MediaState},
    spectrum::AudioSpectrum,
};
use crate::services::{
    broadcast::{BroadcastPayload, BroadcastServer},
    signalrgb::SignalRgbClient,
    steelseries::{GgStatus, SteelSeriesClient},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PreviewTarget {
    LiveAuto,
    Clock,
    Player,
    HwMonitor,
    Volume,
    Calculator,
}

impl Default for PreviewTarget {
    fn default() -> Self {
        Self::LiveAuto
    }
}

#[derive(Clone, Debug)]
pub struct FrameSnapshot {
    pub pixels: [u8; OLED_BYTES],
    pub active_view: String,
    pub render_us: u64,
    pub gg_status: GgStatus,
    pub ram_mb: f32,
}

impl Default for FrameSnapshot {
    fn default() -> Self {
        Self {
            pixels: [0u8; OLED_BYTES],
            active_view: "CLOCK".to_string(),
            render_us: 0,
            gg_status: GgStatus::WaitingForGg,
            ram_mb: 0.0,
        }
    }
}

pub struct EngineHandle {
    pub config: Arc<RwLock<AppConfig>>,
    pub snapshot: Arc<RwLock<FrameSnapshot>>,
    pub preview_target: Arc<RwLock<PreviewTarget>>,
    pub media_state: Arc<RwLock<MediaState>>,
    pub audio_state: Arc<RwLock<AudioState>>,
    pub hw_stats: Arc<RwLock<HwStats>>,
    pub calc_active: Arc<AtomicBool>,
    pub hotkeys: Arc<HotkeyController>,
    pub fps_monitor: Arc<FpsMonitor>,
    pub headset_hid: Arc<HeadsetHid>,
    pub audio_spectrum: Arc<AudioSpectrum>,
    pub force_gg_reconnect: Arc<AtomicBool>,
    pub stop_flag: Arc<AtomicBool>,
    hw_polling_ms: Arc<AtomicU64>,
    show_fps: Arc<AtomicBool>,
    broadcast_server: Arc<Mutex<Option<BroadcastServer>>>,
    broadcast_payload: Arc<RwLock<BroadcastPayload>>,
}

impl EngineHandle {
    pub fn start(initial_cfg: AppConfig) -> Self {
        let stop_flag = Arc::new(AtomicBool::new(false));
        let hw_polling_ms = Arc::new(AtomicU64::new(initial_cfg.hw_polling_ms));
        let show_fps = Arc::new(AtomicBool::new(initial_cfg.show_game_fps));

        let fps_monitor = Arc::new(FpsMonitor::new());
        fps_monitor.set_enabled(initial_cfg.show_game_fps);

        let (hotkeys, hotkey_rx) = start_hotkey_hook(
            &initial_cfg.hotkey_monitor,
            &initial_cfg.hotkey_mute,
            &initial_cfg.hotkey_mute_2,
            &initial_cfg.hotkey_calculator,
        );
        let calc_active = hotkeys.calc_active.clone();
        let hotkeys = Arc::new(hotkeys);

        let config = Arc::new(RwLock::new(initial_cfg.clone()));
        let snapshot = Arc::new(RwLock::new(FrameSnapshot::default()));
        let preview_target = Arc::new(RwLock::new(PreviewTarget::LiveAuto));
        let media_state = Arc::new(RwLock::new(MediaState::default()));
        let audio_state = Arc::new(RwLock::new(AudioState::default()));
        let hw_stats = Arc::new(RwLock::new(HwStats::default()));
        let broadcast_payload = Arc::new(RwLock::new(BroadcastPayload::default()));

        start_smtc_poller(media_state.clone(), stop_flag.clone());
        let audio_tx = start_audio_poller(audio_state.clone(), stop_flag.clone());
        let headset_hid = Arc::new(HeadsetHid::new(audio_tx.clone()));
        headset_hid.set_enabled(initial_cfg.headset_hid_sync_enabled || initial_cfg.show_headset_battery);
        let audio_spectrum = Arc::new(AudioSpectrum::start());
        let force_gg_reconnect = Arc::new(AtomicBool::new(false));

        start_hw_poller(
            hw_stats.clone(),
            hw_polling_ms.clone(),
            show_fps.clone(),
            fps_monitor.clone(),
            stop_flag.clone(),
        );

        let b_srv = if initial_cfg.smtc_broadcast_enabled {
            BroadcastServer::start(initial_cfg.smtc_broadcast_port, broadcast_payload.clone())
        } else {
            None
        };
        let broadcast_server = Arc::new(Mutex::new(b_srv));

        let handle = Self {
            config: config.clone(),
            snapshot: snapshot.clone(),
            preview_target: preview_target.clone(),
            media_state: media_state.clone(),
            audio_state: audio_state.clone(),
            hw_stats: hw_stats.clone(),
            calc_active: calc_active.clone(),
            hotkeys,
            fps_monitor,
            headset_hid: headset_hid.clone(),
            audio_spectrum: audio_spectrum.clone(),
            force_gg_reconnect: force_gg_reconnect.clone(),
            stop_flag: stop_flag.clone(),
            hw_polling_ms,
            show_fps,
            broadcast_server,
            broadcast_payload: broadcast_payload.clone(),
        };

        spawn_render_loop(
            config,
            snapshot,
            preview_target,
            media_state,
            audio_state,
            hw_stats,
            calc_active,
            headset_hid,
            audio_spectrum,
            hotkey_rx,
            audio_tx,
            broadcast_payload,
            force_gg_reconnect,
            stop_flag,
        );

        handle
    }

    pub fn apply_config(&self, new_cfg: &AppConfig) {
        self.hw_polling_ms
            .store(new_cfg.hw_polling_ms, Ordering::Relaxed);
        self.show_fps
            .store(new_cfg.show_game_fps, Ordering::Relaxed);
        self.fps_monitor.set_enabled(new_cfg.show_game_fps);
        self.headset_hid
            .set_enabled(new_cfg.headset_hid_sync_enabled || new_cfg.show_headset_battery);
        self.hotkeys.update_vks(
            &new_cfg.hotkey_monitor,
            &new_cfg.hotkey_mute,
            &new_cfg.hotkey_mute_2,
            &new_cfg.hotkey_calculator,
        );
        crate::logging::set_debug_enabled(new_cfg.debug_enabled);

        if let Ok(mut guard) = self.broadcast_server.lock() {
            let currently_port = guard.as_ref().map(|s| s.port);
            if new_cfg.smtc_broadcast_enabled {
                if currently_port != Some(new_cfg.smtc_broadcast_port) {
                    *guard = BroadcastServer::start(
                        new_cfg.smtc_broadcast_port,
                        self.broadcast_payload.clone(),
                    );
                }
            } else if guard.is_some() {
                *guard = None;
            }
        }
    }

    pub fn shutdown(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
        self.hotkeys.stop();
        self.fps_monitor.stop();
        self.headset_hid.stop();
        self.audio_spectrum.stop();
        if let Ok(mut guard) = self.broadcast_server.lock() {
            *guard = None;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn spawn_render_loop(
    config: Arc<RwLock<AppConfig>>,
    snapshot: Arc<RwLock<FrameSnapshot>>,
    preview_target: Arc<RwLock<PreviewTarget>>,
    media_state: Arc<RwLock<MediaState>>,
    audio_state: Arc<RwLock<AudioState>>,
    hw_stats: Arc<RwLock<HwStats>>,
    calc_active: Arc<AtomicBool>,
    headset_hid: Arc<HeadsetHid>,
    audio_spectrum: Arc<AudioSpectrum>,
    hotkey_rx: Receiver<HotkeyAction>,
    audio_tx: std::sync::mpsc::Sender<AudioCommand>,
    broadcast_payload: Arc<RwLock<BroadcastPayload>>,
    force_gg_reconnect: Arc<AtomicBool>,
    stop_flag: Arc<AtomicBool>,
) {
    thread::Builder::new()
        .name("OLED-Engine".to_string())
        .spawn(move || {
            let mut ss_client = SteelSeriesClient::new();
            let mut srgb_client = SignalRgbClient::new();
            let mut canvas = Canvas128x40::new();
            let mut player = PlayerView::default();
            let mut calc = CalculatorView::new();

            let mut hw_peek_until: Option<Instant> = None;
            let mut last_sent_frame: Option<[u8; OLED_BYTES]> = None;
            let mut last_frame_sent_at = Instant::now() - Duration::from_secs(5);
            let mut last_heartbeat_at = Instant::now();
            let mut last_rgb_at = Instant::now() - Duration::from_secs(5);
            let mut last_ram_check = Instant::now() - Duration::from_secs(10);
            let mut cached_ram_mb = process_memory_mb();
            let mut last_track_sig = String::new();
            let mut last_pos_tick = Instant::now();
            let mut prev_output_to_oled = false;
            let mut sub_tick: u32 = 0;

            while !stop_flag.load(Ordering::Relaxed) {
                let tick_start = Instant::now();
                let dt_ms = tick_start.duration_since(last_pos_tick).as_secs_f64() * 1000.0;
                last_pos_tick = tick_start;
                sub_tick = sub_tick.wrapping_add(1);

                // 1. Drain hotkey actions
                while let Ok(act) = hotkey_rx.try_recv() {
                    match act {
                        HotkeyAction::TriggerMonitor => {
                            hw_peek_until = Some(Instant::now() + Duration::from_secs(3));
                        }
                        HotkeyAction::ToggleMute => {
                            let _ = audio_tx.send(AudioCommand::ToggleMicMute);
                        }
                        HotkeyAction::CalcToggle(on) => {
                            if on {
                                calc.clear();
                            }
                        }
                        HotkeyAction::CalcInput(k) => {
                            calc.key_input(&k);
                        }
                    }
                }

                let cfg = config.read().unwrap().clone();
                let target = *preview_target.read().unwrap();
                let media = media_state.read().unwrap().clone();
                let audio = audio_state.read().unwrap().clone();
                let hw = hw_stats.read().unwrap().clone();

                // Sync SMTC broadcast payload + SignalRGB push
                if let Ok(mut bp) = broadcast_payload.write() {
                    bp.playing = media.playing;
                    bp.title = media.title.clone();
                    bp.artist = media.artist.clone();
                    bp.album = media.album.clone();
                    bp.cover_bytes = media.cover_bytes.clone();
                    bp.cover_mime = "image/jpeg".to_string();
                }
                srgb_client.maybe_push(
                    cfg.signalrgb_push_enabled,
                    cfg.signalrgb_push_port,
                    &cfg.signalrgb_push_sender,
                    cfg.signalrgb_push_include_title,
                    media.playing,
                    &media.title,
                    &media.artist,
                    &media.album,
                    media.cover_bytes.as_deref(),
                    &media.cover_colors,
                );

                // Update player state from live SMTC (or demo fallback in explicit Player preview)
                let track_sig = format!("{}|{}", media.artist, media.title);
                if media.active {
                    let rate = if media.playback_rate > 0.0 {
                        media.playback_rate
                    } else {
                        1.0
                    };
                    let dur_ms = media.duration_ms.max(1);
                    let live_pos_ms = if media.playing {
                        let extra = media
                            .position_updated_at
                            .map(|t| (t.elapsed().as_secs_f64() * rate * 1000.0).round() as u64)
                            .unwrap_or(0);
                        media.position_ms.saturating_add(extra).min(dur_ms)
                    } else {
                        media.position_ms.min(dur_ms)
                    };

                    if track_sig != last_track_sig {
                        last_track_sig = track_sig;
                        player.update_track(
                            &media.title,
                            &media.artist,
                            live_pos_ms,
                            dur_ms,
                            !media.playing,
                            media.source.unwrap_or(MediaSource::Generic),
                        );
                    } else {
                        player.paused = !media.playing;
                        player.duration_ms = dur_ms;
                        if !media.playing {
                            player.position_ms = live_pos_ms;
                        } else {
                            player.position_ms = player
                                .position_ms
                                .saturating_add((dt_ms * rate).round() as u64)
                                .min(dur_ms);
                            let diff = live_pos_ms as i64 - player.position_ms as i64;
                            if diff.abs() > 1500 || diff > 250 {
                                player.position_ms = live_pos_ms;
                            }
                        }
                    }
                }
                let want_spectrum = cfg.player_style == PlayerStyle::SpectrumTicker
                    && (target == PreviewTarget::Player
                        || (target == PreviewTarget::LiveAuto
                            && cfg.display_player
                            && media.active
                            && media.playing));
                audio_spectrum.set_active(want_spectrum);

                if !want_spectrum || (sub_tick % 2 == 0) {
                    player.tick_scroll();
                }

                if want_spectrum {
                    let (bands, peaks) = audio_spectrum.read();
                    player.set_spectrum(bands, peaks);
                }

                // 2. Render active OLED view
                let render_start = Instant::now();
                let view_name: &str;

                match target {
                    PreviewTarget::Clock => {
                        let batt = if cfg.show_headset_battery {
                            headset_hid.current_battery().or(Some(82))
                        } else {
                            None
                        };
                        render_clock(
                            &mut canvas,
                            &ClockViewOpts {
                                style: cfg.clock_style,
                                use_24h: cfg.use_24h,
                                display_seconds: cfg.display_seconds,
                                use_turkish_days: cfg.use_turkish_days,
                                battery_pct: batt,
                                show_battery_percent: cfg.show_battery_percent,
                            },
                        );
                        view_name = "CLOCK (PREVIEW)";
                    }
                    PreviewTarget::Player => {
                        if !media.active {
                            let mut demo = PlayerView::default();
                            demo.update_track(
                                "Midnight City",
                                "M83",
                                84_000,
                                215_000,
                                false,
                                MediaSource::Spotify,
                            );
                            demo.step = player.step;
                            if cfg.player_style == PlayerStyle::SpectrumTicker {
                                let (bands, peaks) = audio_spectrum.read();
                                let has_audio = bands.iter().any(|&b| b > 0.02);
                                if has_audio {
                                    demo.set_spectrum(bands, peaks);
                                } else {
                                    let mut db = [0.0f32; SPECTRUM_BANDS];
                                    let mut dp = [0.0f32; SPECTRUM_BANDS];
                                    for i in 0..SPECTRUM_BANDS {
                                        let v = (((sub_tick as f32 * 0.25 + i as f32 * 0.55).sin() + 1.0) * 0.35 + 0.15).clamp(0.1, 0.9);
                                        db[i] = v;
                                        dp[i] = (v + 0.12).min(0.98);
                                    }
                                    demo.set_spectrum(db, dp);
                                }
                            }
                            demo.render(&mut canvas, cfg.player_style);
                        } else {
                            player.render(&mut canvas, cfg.player_style);
                        }
                        view_name = "PLAYER (PREVIEW)";
                    }
                    PreviewTarget::HwMonitor => {
                        render_hw(&mut canvas, &hw, cfg.hw_style);
                        view_name = "HW MONITOR (PREVIEW)";
                    }
                    PreviewTarget::Volume => {
                        render_volume(&mut canvas, audio.speaker_vol, audio.speaker_muted, audio.mic_muted);
                        view_name = "VOLUME (PREVIEW)";
                    }
                    PreviewTarget::Calculator => {
                        let mut demo_calc = calc.clone();
                        if demo_calc == CalculatorView::new() {
                            demo_calc.set_demo_state("(128+40)*2 =", "336");
                        }
                        demo_calc.render(&mut canvas);
                        view_name = "CALCULATOR (PREVIEW)";
                    }
                    PreviewTarget::LiveAuto => {
                        let show_vol = audio
                            .last_change
                            .map(|t| t.elapsed() < Duration::from_millis(1500))
                            .unwrap_or(false);
                        let show_hw_peek = hw_peek_until.map(|u| Instant::now() < u).unwrap_or(false);

                        if calc_active.load(Ordering::Relaxed) {
                            calc.render(&mut canvas);
                            view_name = "CALCULATOR";
                        } else if cfg.display_hw_monitor || show_hw_peek {
                            render_hw(&mut canvas, &hw, cfg.hw_style);
                            view_name = "HW MONITOR";
                        } else if show_vol {
                            render_volume(
                                &mut canvas,
                                audio.speaker_vol,
                                audio.speaker_muted,
                                audio.mic_muted,
                            );
                            view_name = "VOLUME";
                        } else if cfg.display_player && media.active && media.playing {
                            player.render(&mut canvas, cfg.player_style);
                            view_name = "PLAYER";
                        } else if cfg.display_clock {
                            let batt = if cfg.show_headset_battery {
                                headset_hid.current_battery()
                            } else {
                                None
                            };
                            render_clock(
                                &mut canvas,
                                &ClockViewOpts {
                                    style: cfg.clock_style,
                                    use_24h: cfg.use_24h,
                                    display_seconds: cfg.display_seconds,
                                    use_turkish_days: cfg.use_turkish_days,
                                    battery_pct: batt,
                                    show_battery_percent: cfg.show_battery_percent,
                                },
                            );
                            view_name = "CLOCK";
                        } else {
                            canvas.clear();
                            view_name = "IDLE";
                        }
                    }
                }
                let render_us = render_start.elapsed().as_micros() as u64;

                // 3. Push to SteelSeries GameSense if enabled & outputting
                if cfg.enabled && cfg.output_to_oled {
                    if force_gg_reconnect.swap(false, Ordering::Relaxed)
                        || (!prev_output_to_oled && last_sent_frame.is_some())
                    {
                        ss_client.reconnect();
                        last_sent_frame = None;
                    }
                    let changed = last_sent_frame.as_ref() != Some(&canvas.data);
                    let keepalive = last_frame_sent_at.elapsed() >= Duration::from_secs(1);
                    if changed || keepalive {
                        if ss_client.send_frame(&canvas.data) {
                            last_sent_frame = Some(canvas.data);
                            last_frame_sent_at = Instant::now();
                        }
                    }

                    if cfg.rgb_enabled && last_rgb_at.elapsed() >= Duration::from_secs(1) {
                        last_rgb_at = Instant::now();
                        ss_client.send_rgb(cfg.rgb_color[0], cfg.rgb_color[1], cfg.rgb_color[2]);
                    }

                    if last_heartbeat_at.elapsed() >= Duration::from_secs(30) {
                        last_heartbeat_at = Instant::now();
                        ss_client.heartbeat();
                    }
                } else {
                    ss_client.status = GgStatus::Paused;
                }
                prev_output_to_oled = cfg.output_to_oled;

                if last_ram_check.elapsed() >= Duration::from_secs(1) {
                    last_ram_check = Instant::now();
                    cached_ram_mb = process_memory_mb();
                }

                if let Ok(mut snap) = snapshot.write() {
                    snap.pixels = canvas.data;
                    snap.active_view = view_name.to_string();
                    snap.render_us = render_us;
                    snap.gg_status = ss_client.status.clone();
                    snap.ram_mb = cached_ram_mb;
                }

                let frame_period = if want_spectrum {
                    Duration::from_millis(50)
                } else {
                    Duration::from_millis(100)
                };
                let elapsed = tick_start.elapsed();
                if elapsed < frame_period {
                    thread::sleep(frame_period - elapsed);
                }
            }
        })
        .expect("spawn OLED-Engine");
}
