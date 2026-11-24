#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod engine;
mod ipc;
mod logging;
mod oled;
mod platform;
mod services;
mod ui;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;

use eframe::egui;
use tray_icon::menu::MenuEvent;
use tray_icon::{MouseButton, TrayIconEvent};
use windows::core::w;
use windows::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, LPARAM, WPARAM};
use windows::Win32::System::Threading::CreateMutexW;
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, FindWindowW, PeekMessageW, PostMessageW, TranslateMessage, MSG, PM_REMOVE,
    WM_CLOSE,
};

use config::AppConfig;
use engine::EngineHandle;
use ipc::{read_running_port, start_ipc_server, DaemonEvent, IpcClient};
use platform::hardware::{process_memory_mb, trim_working_set};
use platform::startup::{
    is_running_as_admin, is_startup_enabled, relaunch_as_admin, set_startup_enabled,
    sync_startup_task_path_if_needed,
};
use services::steelseries::SteelSeriesClient;
use ui::tray::{create_tray, load_window_icon_rgba, spawn_or_focus_ui, TrayState};
use ui::OledApp;

fn current_exe_mtime() -> u64 {
    std::env::current_exe()
        .ok()
        .and_then(|p| std::fs::metadata(p).ok())
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn run_smoke_test() {
    let mut cfg = AppConfig::load();
    // Never disrupt a live SteelSeries GG registration or broadcast port during smoke test
    cfg.output_to_oled = false;
    cfg.smtc_broadcast_enabled = false;
    cfg.signalrgb_push_enabled = false;
    let engine = EngineHandle::start(cfg);
    thread::sleep(Duration::from_millis(1600));
    trim_working_set();
    thread::sleep(Duration::from_millis(200));

    let snap = engine.snapshot.read().unwrap().clone();
    let hw = engine.hw_stats.read().unwrap().clone();
    let media = engine.media_state.read().unwrap().clone();
    let audio = engine.audio_state.read().unwrap().clone();
    let ram = process_memory_mb();

    println!("=== OLED Customizer v{} Smoke Test ===", env!("CARGO_PKG_VERSION"));
    println!("Running as Admin        : {}", is_running_as_admin());
    println!(
        "coreProps.json detected : {}",
        SteelSeriesClient::coreprops_exists()
    );
    println!("GameSense Status        : {}", snap.gg_status.label());
    println!(
        "CPU                     : {}% ({})",
        hw.cpu_load_pct,
        hw.cpu_temp_c
            .map(|t| format!("{}°C", t))
            .unwrap_or_else(|| "temp N/A (needs Admin)".into())
    );
    println!(
        "GPU                     : {} ({}, {})",
        hw.gpu_name,
        hw.gpu_temp_c
            .map(|t| format!("{}°C", t))
            .unwrap_or_else(|| "--".into()),
        hw.gpu_load_pct
            .map(|l| format!("{}%", l))
            .unwrap_or_else(|| "--".into())
    );
    println!(
        "RAM                     : {:.1} / {:.1} GB ({}%)",
        hw.ram_used_gb, hw.ram_total_gb, hw.ram_pct
    );
    println!(
        "Game FPS                : {:?} (status: {})",
        hw.fps, hw.fps_status
    );
    println!(
        "Headset HID             : {}",
        engine.headset_hid.status_summary()
    );
    println!(
        "Audio                   : Speaker={} ({}% muted={}), Mic muted={:?}",
        audio.has_speaker, audio.speaker_vol, audio.speaker_muted, audio.mic_muted
    );
    println!(
        "SMTC Media              : active={}, playing={}, title=\"{}\"",
        media.active, media.playing, media.title
    );
    println!("Active OLED View        : {}", snap.active_view);
    println!(
        "Render Time             : {} us ({:.3} ms)",
        snap.render_us,
        snap.render_us as f32 / 1000.0
    );
    println!("Daemon Working Set      : {:.2} MB", ram);

    engine.shutdown();
}

fn run_ui_process(port: u16) {
    let client = IpcClient::new(port);
    let initial = client.get_state().unwrap_or_default();

    let (icon_rgba, iw, ih) = load_window_icon_rgba();
    let viewport = egui::ViewportBuilder::default()
        .with_inner_size([900.0, 670.0])
        .with_min_inner_size([780.0, 560.0])
        .with_title("OLED Customizer")
        .with_icon(egui::IconData {
            rgba: icon_rgba,
            width: iw,
            height: ih,
        });

    let options = eframe::NativeOptions {
        viewport,
        ..Default::default()
    };

    let _ = eframe::run_native(
        "OLED Customizer",
        options,
        Box::new(move |cc| Ok(Box::new(OledApp::new(cc, client, initial)))),
    );
}

fn sync_tray_checks(tray: &TrayState, cfg: &AppConfig, calc_active: bool) {
    tray.item_enabled.set_checked(cfg.enabled);
    tray.item_hw_always.set_checked(cfg.display_hw_monitor);
    tray.item_fps.set_checked(cfg.show_game_fps);
    tray.item_calc.set_checked(calc_active);
    for (st, it) in &tray.clock_items {
        it.set_checked(*st == cfg.clock_style);
    }
    for (st, it) in &tray.player_items {
        it.set_checked(*st == cfg.player_style);
    }
    for (st, it) in &tray.hw_items {
        it.set_checked(*st == cfg.hw_style);
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.iter().any(|a| a == "--smoke-test") {
        let cfg = AppConfig::load();
        logging::init_logging(cfg.debug_enabled);
        run_smoke_test();
        return;
    }

    if args.iter().any(|a| a == "--ui") {
        let port = args
            .windows(2)
            .find(|w| w[0] == "--ipc-port")
            .and_then(|w| w[1].parse::<u16>().ok())
            .or_else(read_running_port)
            .unwrap_or(0);
        if port != 0 {
            run_ui_process(port);
        }
        return;
    }

    let start_minimized_arg = args.iter().any(|a| a == "--minimized");
    let setup_admin_task = args.iter().any(|a| a == "--setup-admin-task");
    let elevated_relaunch = setup_admin_task || args.iter().any(|a| a == "--elevated");
    let restart_arg = args.iter().any(|a| a == "--restart");
    let no_elevate = args.iter().any(|a| a == "--no-elevate");
    let exe_mtime = current_exe_mtime();

    let cfg = AppConfig::load();
    logging::init_logging(cfg.debug_enabled);

    if setup_admin_task && is_running_as_admin() {
        if let Err(e) = set_startup_enabled(true, true) {
            log::error!("Failed to register Admin Task Scheduler entry: {}", e);
        } else {
            log::info!("Registered 'OLED Customizer' Task Scheduler entry (Admin at Logon)");
        }
    }

    // Single-instance guard (supports Smart Replace when a newer/different exe is launched)
    let mut attempts = if elevated_relaunch || restart_arg { 25 } else { 1 };
    let mut replace_requested = false;
    let _mutex = loop {
        let acquired = unsafe {
            match CreateMutexW(None, false, w!("OLED_Customizer_Mutex")) {
                Ok(handle) => {
                    if GetLastError() == ERROR_ALREADY_EXISTS {
                        let _ = CloseHandle(handle);
                        None
                    } else {
                        Some(handle)
                    }
                }
                Err(_) => None,
            }
        };
        if let Some(handle) = acquired {
            break handle;
        }
        if !elevated_relaunch && !replace_requested {
            if let Some(p) = read_running_port() {
                let is_different = restart_arg
                    || IpcClient::get_meta(p)
                        .map(|(ver, mtime)| ver != env!("CARGO_PKG_VERSION") || mtime != exe_mtime)
                        .unwrap_or(false);
                if is_different {
                    replace_requested = true;
                    attempts = 25;
                    let _ = IpcClient::request_quit(p);
                } else {
                    let _ = IpcClient::wake_open_ui(p);
                    return;
                }
            } else {
                return;
            }
        }
        attempts -= 1;
        if attempts == 0 {
            if let Some(p) = read_running_port() {
                let _ = IpcClient::wake_open_ui(p);
            }
            return;
        }
        thread::sleep(Duration::from_millis(150));
    };

    // If Task Scheduler Admin mode is active, auto-elevate on manual cold starts too
    if !is_running_as_admin() && !elevated_relaunch && !no_elevate && is_startup_enabled() {
        let elevate_args = if start_minimized_arg {
            "--elevated --minimized"
        } else {
            "--elevated"
        };
        if relaunch_as_admin(elevate_args) {
            unsafe {
                let _ = CloseHandle(_mutex);
            }
            return;
        }
    }

    if is_running_as_admin() && !setup_admin_task {
        thread::spawn(|| {
            sync_startup_task_path_if_needed();
        });
    }

    let stop_flag = Arc::new(AtomicBool::new(false));
    let engine = Arc::new(EngineHandle::start(cfg.clone()));
    let (daemon_tx, daemon_rx) = mpsc::channel::<DaemonEvent>();
    let ipc_port = start_ipc_server(engine.clone(), daemon_tx, stop_flag.clone(), exe_mtime).unwrap_or(0);

    let tray = create_tray(&cfg).ok();

    let start_minimized = start_minimized_arg || (cfg.start_minimized && !elevated_relaunch);
    if !start_minimized && ipc_port != 0 {
        spawn_or_focus_ui(ipc_port);
    }

    // Trim initial startup pages after threads settle
    thread::spawn(|| {
        thread::sleep(Duration::from_millis(2000));
        trim_working_set();
    });

    // Pure Win32 headless message loop (no OpenGL/eframe overhead in tray!)
    let mut msg = MSG::default();
    'daemon: loop {
        unsafe {
            while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).into() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }

        while let Ok(ev) = daemon_rx.try_recv() {
            match ev {
                DaemonEvent::OpenUi => {
                    if ipc_port != 0 {
                        spawn_or_focus_ui(ipc_port);
                    }
                }
                DaemonEvent::ConfigChanged => {
                    if let Some(ref tr) = tray {
                        let c = engine.config.read().unwrap().clone();
                        let calc = engine.calc_active.load(Ordering::Relaxed);
                        sync_tray_checks(tr, &c, calc);
                    }
                }
                DaemonEvent::ReconnectGg => {
                    engine.force_gg_reconnect.store(true, Ordering::Relaxed);
                }
                DaemonEvent::Quit => {
                    break 'daemon;
                }
            }
        }

        let mut open_requested = false;
        while let Ok(ev) = TrayIconEvent::receiver().try_recv() {
            if matches!(
                ev,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    ..
                } | TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                }
            ) {
                open_requested = true;
            }
        }

        while let Ok(ev) = MenuEvent::receiver().try_recv() {
            if let Some(ref tr) = tray {
                if ev.id == tr.ids.id_open {
                    open_requested = true;
                } else if ev.id == tr.ids.id_reconnect_gg {
                    engine.force_gg_reconnect.store(true, Ordering::Relaxed);
                } else if ev.id == tr.ids.id_quit {
                    break 'daemon;
                } else {
                    let mut changed = false;
                    {
                        let mut c = engine.config.write().unwrap();
                        if ev.id == tr.ids.id_enabled {
                            c.enabled = !c.enabled;
                            changed = true;
                        } else if ev.id == tr.ids.id_hw_always {
                            c.display_hw_monitor = !c.display_hw_monitor;
                            if c.display_hw_monitor {
                                c.display_clock = false;
                            }
                            changed = true;
                        } else if ev.id == tr.ids.id_fps {
                            c.show_game_fps = !c.show_game_fps;
                            changed = true;
                        } else if ev.id == tr.ids.id_calc {
                            let cur = engine.calc_active.load(Ordering::Relaxed);
                            engine.calc_active.store(!cur, Ordering::Relaxed);
                            tr.item_calc.set_checked(!cur);
                        } else {
                            for (st, id) in &tr.ids.clock_ids {
                                if ev.id == *id {
                                    c.clock_style = *st;
                                    changed = true;
                                }
                            }
                            for (st, id) in &tr.ids.player_ids {
                                if ev.id == *id {
                                    c.player_style = *st;
                                    changed = true;
                                }
                            }
                            for (st, id) in &tr.ids.hw_ids {
                                if ev.id == *id {
                                    c.hw_style = *st;
                                    changed = true;
                                }
                            }
                        }
                        if changed {
                            let _ = c.save();
                        }
                    }
                    if changed {
                        let c_clone = engine.config.read().unwrap().clone();
                        engine.apply_config(&c_clone);
                        let calc = engine.calc_active.load(Ordering::Relaxed);
                        sync_tray_checks(tr, &c_clone, calc);
                    }
                }
            }
        }

        if open_requested && ipc_port != 0 {
            spawn_or_focus_ui(ipc_port);
        }

        thread::sleep(Duration::from_millis(30));
    }

    // Close any open --ui window cleanly
    unsafe {
        if let Ok(hwnd) = FindWindowW(None, w!("OLED Customizer")) {
            if !hwnd.0.is_null() {
                let _ = PostMessageW(hwnd, WM_CLOSE, WPARAM(0), LPARAM(0));
            }
        }
    }
    stop_flag.store(true, Ordering::Relaxed);
    engine.shutdown();
}
