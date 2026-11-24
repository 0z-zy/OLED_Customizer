use std::process::Command;

use tray_icon::menu::{CheckMenuItem, Menu, MenuId, MenuItem, PredefinedMenuItem, Submenu};
use tray_icon::{Icon, TrayIcon, TrayIconBuilder};
use windows::core::w;
use windows::Win32::UI::WindowsAndMessaging::{
    FindWindowW, SetForegroundWindow, ShowWindow, SW_RESTORE, SW_SHOW,
};

use crate::config::AppConfig;
use crate::oled::views::{clock::ClockStyle, hw_monitor::HwStyle, player::PlayerStyle};

static TRAY_ICON_PNG: &[u8] = include_bytes!("../../assets/tray_icon.png");
static APP_ICON_PNG: &[u8] = include_bytes!("../../assets/app_icon.png");

#[derive(Clone)]
pub struct TrayIds {
    pub id_open: MenuId,
    pub id_reconnect_gg: MenuId,
    pub id_quit: MenuId,
    pub id_enabled: MenuId,
    pub id_hw_always: MenuId,
    pub id_fps: MenuId,
    pub id_calc: MenuId,
    pub clock_ids: Vec<(ClockStyle, MenuId)>,
    pub player_ids: Vec<(PlayerStyle, MenuId)>,
    pub hw_ids: Vec<(HwStyle, MenuId)>,
}

pub struct TrayState {
    pub _tray: TrayIcon,
    pub ids: TrayIds,
    pub item_enabled: CheckMenuItem,
    pub item_hw_always: CheckMenuItem,
    pub item_fps: CheckMenuItem,
    pub item_calc: CheckMenuItem,
    pub clock_items: Vec<(ClockStyle, CheckMenuItem)>,
    pub player_items: Vec<(PlayerStyle, CheckMenuItem)>,
    pub hw_items: Vec<(HwStyle, CheckMenuItem)>,
}

pub fn load_tray_icon_rgba() -> (Vec<u8>, u32, u32) {
    let img = image::load_from_memory(TRAY_ICON_PNG)
        .expect("embedded tray_icon.png")
        .into_rgba8();
    let (w, h) = img.dimensions();
    (img.into_raw(), w, h)
}

pub fn load_window_icon_rgba() -> (Vec<u8>, u32, u32) {
    let img = image::load_from_memory(APP_ICON_PNG)
        .expect("embedded app_icon.png")
        .resize(128, 128, image::imageops::FilterType::Lanczos3)
        .into_rgba8();
    let (w, h) = img.dimensions();
    (img.into_raw(), w, h)
}

pub fn spawn_or_focus_ui(ipc_port: u16) {
    unsafe {
        if let Ok(hwnd) = FindWindowW(None, w!("OLED Customizer")) {
            if !hwnd.0.is_null() {
                let _ = ShowWindow(hwnd, SW_SHOW);
                let _ = ShowWindow(hwnd, SW_RESTORE);
                let _ = SetForegroundWindow(hwnd);
                return;
            }
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        let _ = Command::new(exe)
            .args(["--ui", "--ipc-port", &ipc_port.to_string()])
            .spawn();
    }
}

pub fn create_tray(cfg: &AppConfig) -> Result<TrayState, String> {
    let (rgba, w, h) = load_tray_icon_rgba();
    let icon = Icon::from_rgba(rgba, w, h).map_err(|e| e.to_string())?;

    let menu = Menu::new();
    let item_open = MenuItem::new("Open Settings & Live Preview", true, None);
    let item_reconnect_gg = MenuItem::new("Reconnect SteelSeries GG", true, None);
    let item_enabled = CheckMenuItem::new("Enable OLED Output", true, cfg.enabled, None);
    let item_hw_always =
        CheckMenuItem::new("Always Show HW Monitor", true, cfg.display_hw_monitor, None);
    let item_fps = CheckMenuItem::new("Show Game FPS", true, cfg.show_game_fps, None);
    let item_calc = CheckMenuItem::new("Calculator Mode", true, false, None);
    let item_quit = MenuItem::new("Quit", true, None);

    let clock_sub = Submenu::new("Clock Style", true);
    let mut clock_items = Vec::new();
    let mut clock_ids = Vec::new();
    for st in ClockStyle::ALL {
        let it = CheckMenuItem::new(st.label(), true, cfg.clock_style == st, None);
        let _ = clock_sub.append(&it);
        clock_ids.push((st, it.id().clone()));
        clock_items.push((st, it));
    }

    let player_sub = Submenu::new("Player Style", true);
    let mut player_items = Vec::new();
    let mut player_ids = Vec::new();
    for st in PlayerStyle::ALL {
        let it = CheckMenuItem::new(st.label(), true, cfg.player_style == st, None);
        let _ = player_sub.append(&it);
        player_ids.push((st, it.id().clone()));
        player_items.push((st, it));
    }

    let hw_sub = Submenu::new("HW Monitor Style", true);
    let mut hw_items = Vec::new();
    let mut hw_ids = Vec::new();
    for st in HwStyle::ALL {
        let it = CheckMenuItem::new(st.label(), true, cfg.hw_style == st, None);
        let _ = hw_sub.append(&it);
        hw_ids.push((st, it.id().clone()));
        hw_items.push((st, it));
    }

    let _ = menu.append(&item_open);
    let _ = menu.append(&item_reconnect_gg);
    let _ = menu.append(&PredefinedMenuItem::separator());
    let _ = menu.append(&item_enabled);
    let _ = menu.append(&clock_sub);
    let _ = menu.append(&player_sub);
    let _ = menu.append(&hw_sub);
    let _ = menu.append(&item_hw_always);
    let _ = menu.append(&item_fps);
    let _ = menu.append(&item_calc);
    let _ = menu.append(&PredefinedMenuItem::separator());
    let _ = menu.append(&item_quit);

    let tray = TrayIconBuilder::new()
        .with_menu(Box::new(menu))
        .with_tooltip("OLED Customizer")
        .with_icon(icon)
        .build()
        .map_err(|e| e.to_string())?;

    let ids = TrayIds {
        id_open: item_open.id().clone(),
        id_reconnect_gg: item_reconnect_gg.id().clone(),
        id_quit: item_quit.id().clone(),
        id_enabled: item_enabled.id().clone(),
        id_hw_always: item_hw_always.id().clone(),
        id_fps: item_fps.id().clone(),
        id_calc: item_calc.id().clone(),
        clock_ids,
        player_ids,
        hw_ids,
    };

    Ok(TrayState {
        _tray: tray,
        ids,
        item_enabled,
        item_hw_always,
        item_fps,
        item_calc,
        clock_items,
        player_items,
        hw_items,
    })
}
