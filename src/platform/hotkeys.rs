use std::sync::{
    atomic::{AtomicBool, AtomicU32, Ordering},
    mpsc::{self, Receiver, Sender},
    Arc, OnceLock,
};
use std::thread;

use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::System::Threading::GetCurrentThreadId;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    VK_BACK, VK_DELETE, VK_ESCAPE, VK_LCONTROL, VK_LSHIFT, VK_RCONTROL, VK_RETURN, VK_RSHIFT,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, DispatchMessageW, GetMessageW, PostThreadMessageW, SetWindowsHookExW,
    TranslateMessage, UnhookWindowsHookEx, HHOOK, KBDLLHOOKSTRUCT, MSG, MSLLHOOKSTRUCT,
    WH_KEYBOARD_LL, WH_MOUSE_LL, WM_KEYDOWN, WM_KEYUP, WM_QUIT, WM_SYSKEYDOWN, WM_SYSKEYUP,
    WM_XBUTTONDOWN,
};

#[derive(Clone, Debug)]
pub enum HotkeyAction {
    TriggerMonitor,
    ToggleMute,
    CalcToggle(bool),
    CalcInput(String),
}

pub struct HotkeyController {
    pub vk_monitor: Arc<AtomicU32>,
    pub vk_mute: Arc<AtomicU32>,
    pub vk_mute_2: Arc<AtomicU32>,
    pub vk_calc: Arc<AtomicU32>,
    pub calc_active: Arc<AtomicBool>,
    hook_tid: Arc<AtomicU32>,
}

impl HotkeyController {
    pub fn update_vks(&self, monitor: &str, mute: &str, mute2: &str, calc: &str) {
        self.vk_monitor
            .store(key_str_to_vk(monitor).unwrap_or(0), Ordering::Relaxed);
        self.vk_mute
            .store(key_str_to_vk(mute).unwrap_or(0), Ordering::Relaxed);
        self.vk_mute_2
            .store(key_str_to_vk(mute2).unwrap_or(0), Ordering::Relaxed);
        self.vk_calc
            .store(key_str_to_vk(calc).unwrap_or(0), Ordering::Relaxed);
    }

    pub fn stop(&self) {
        let tid = self.hook_tid.load(Ordering::Relaxed);
        if tid != 0 {
            unsafe {
                let _ = PostThreadMessageW(tid, WM_QUIT, WPARAM(0), LPARAM(0));
            }
        }
    }
}

pub fn key_str_to_vk(s: &str) -> Option<u32> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Some(name) = trimmed.strip_prefix("Key.") {
        return match name.to_ascii_lowercase().as_str() {
            "insert" => Some(0x2D),
            "delete" => Some(0x2E),
            "home" => Some(0x24),
            "end" => Some(0x23),
            "page_up" => Some(0x21),
            "page_down" => Some(0x22),
            "pause" => Some(0x13),
            "scroll_lock" => Some(0x91),
            "print_screen" => Some(0x2C),
            "caps_lock" => Some(0x14),
            "num_lock" => Some(0x90),
            "space" => Some(0x20),
            "enter" => Some(0x0D),
            "backspace" => Some(0x08),
            "tab" => Some(0x09),
            "esc" => Some(0x1B),
            "up" => Some(0x26),
            "down" => Some(0x28),
            "left" => Some(0x25),
            "right" => Some(0x27),
            "mouse_4" => Some(0x05),
            "mouse_5" => Some(0x06),
            "f1" => Some(0x70),
            "f2" => Some(0x71),
            "f3" => Some(0x72),
            "f4" => Some(0x73),
            "f5" => Some(0x74),
            "f6" => Some(0x75),
            "f7" => Some(0x76),
            "f8" => Some(0x77),
            "f9" => Some(0x78),
            "f10" => Some(0x79),
            "f11" => Some(0x7A),
            "f12" => Some(0x7B),
            _ => None,
        };
    }
    if trimmed.len() == 1 {
        let ch = trimmed.chars().next().unwrap().to_ascii_uppercase();
        if ch.is_ascii_alphanumeric() {
            return Some(ch as u32);
        }
    }
    None
}

struct HookCtx {
    tx: Sender<HotkeyAction>,
    vk_monitor: Arc<AtomicU32>,
    vk_mute: Arc<AtomicU32>,
    vk_mute_2: Arc<AtomicU32>,
    vk_calc: Arc<AtomicU32>,
    calc_active: Arc<AtomicBool>,
    ctrl_held: AtomicBool,
    shift_held: AtomicBool,
}

static HOOK_CTX: OnceLock<HookCtx> = OnceLock::new();

pub fn start_hotkey_hook(
    monitor: &str,
    mute: &str,
    mute2: &str,
    calc: &str,
) -> (HotkeyController, Receiver<HotkeyAction>) {
    let (tx, rx) = mpsc::channel();
    let vk_monitor = Arc::new(AtomicU32::new(key_str_to_vk(monitor).unwrap_or(0)));
    let vk_mute = Arc::new(AtomicU32::new(key_str_to_vk(mute).unwrap_or(0)));
    let vk_mute_2 = Arc::new(AtomicU32::new(key_str_to_vk(mute2).unwrap_or(0)));
    let vk_calc = Arc::new(AtomicU32::new(key_str_to_vk(calc).unwrap_or(0)));
    let calc_active = Arc::new(AtomicBool::new(false));
    let hook_tid = Arc::new(AtomicU32::new(0));

    let _ = HOOK_CTX.set(HookCtx {
        tx,
        vk_monitor: vk_monitor.clone(),
        vk_mute: vk_mute.clone(),
        vk_mute_2: vk_mute_2.clone(),
        vk_calc: vk_calc.clone(),
        calc_active: calc_active.clone(),
        ctrl_held: AtomicBool::new(false),
        shift_held: AtomicBool::new(false),
    });

    let tid_clone = hook_tid.clone();
    thread::Builder::new()
        .name("Hotkey-Hook".to_string())
        .spawn(move || unsafe {
            tid_clone.store(GetCurrentThreadId(), Ordering::Relaxed);
            let k_hook: HHOOK =
                SetWindowsHookExW(WH_KEYBOARD_LL, Some(kb_proc), None, 0).unwrap_or_default();
            let m_hook: HHOOK =
                SetWindowsHookExW(WH_MOUSE_LL, Some(mouse_proc), None, 0).unwrap_or_default();

            let mut msg = MSG::default();
            while GetMessageW(&mut msg, None, 0, 0).into() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }

            if !k_hook.is_invalid() {
                let _ = UnhookWindowsHookEx(k_hook);
            }
            if !m_hook.is_invalid() {
                let _ = UnhookWindowsHookEx(m_hook);
            }
        })
        .expect("spawn Hotkey-Hook");

    (
        HotkeyController {
            vk_monitor,
            vk_mute,
            vk_mute_2,
            vk_calc,
            calc_active,
            hook_tid,
        },
        rx,
    )
}

unsafe extern "system" fn kb_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        if let Some(ctx) = HOOK_CTX.get() {
            let kb = &*(lparam.0 as *const KBDLLHOOKSTRUCT);
            let vk = kb.vkCode;
            let wp = wparam.0 as u32;
            let is_down = wp == WM_KEYDOWN || wp == WM_SYSKEYDOWN;
            let _is_up = wp == WM_KEYUP || wp == WM_SYSKEYUP;

            if vk == VK_LCONTROL.0 as u32 || vk == VK_RCONTROL.0 as u32 {
                ctx.ctrl_held.store(is_down, Ordering::Relaxed);
                return CallNextHookEx(None, code, wparam, lparam);
            }
            if vk == VK_LSHIFT.0 as u32 || vk == VK_RSHIFT.0 as u32 {
                ctx.shift_held.store(is_down, Ordering::Relaxed);
                return CallNextHookEx(None, code, wparam, lparam);
            }

            if is_down {
                let ctrl = ctx.ctrl_held.load(Ordering::Relaxed);
                let calc_vk = ctx.vk_calc.load(Ordering::Relaxed);
                if ctrl && calc_vk != 0 && vk == calc_vk {
                    ctx.ctrl_held.store(false, Ordering::Relaxed);
                    let next = !ctx.calc_active.load(Ordering::Relaxed);
                    ctx.calc_active.store(next, Ordering::Relaxed);
                    let _ = ctx.tx.send(HotkeyAction::CalcToggle(next));
                    return CallNextHookEx(None, code, wparam, lparam);
                }

                if vk == ctx.vk_monitor.load(Ordering::Relaxed) && vk != 0 {
                    let _ = ctx.tx.send(HotkeyAction::TriggerMonitor);
                }
                if (vk == ctx.vk_mute.load(Ordering::Relaxed) && vk != 0)
                    || (vk == ctx.vk_mute_2.load(Ordering::Relaxed) && vk != 0)
                {
                    let _ = ctx.tx.send(HotkeyAction::ToggleMute);
                }

                // Calculator numpad capture & suppression
                if ctx.calc_active.load(Ordering::Relaxed) {
                    if vk == VK_ESCAPE.0 as u32 {
                        ctx.calc_active.store(false, Ordering::Relaxed);
                        let _ = ctx.tx.send(HotkeyAction::CalcToggle(false));
                        return LRESULT(1);
                    }
                    if let Some(key) = map_calc_vk(vk, kb.flags.0, ctx.shift_held.load(Ordering::Relaxed)) {
                        let _ = ctx.tx.send(HotkeyAction::CalcInput(key));
                        return LRESULT(1);
                    }
                }
            }
        }
    }
    CallNextHookEx(None, code, wparam, lparam)
}

unsafe extern "system" fn mouse_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 && wparam.0 as u32 == WM_XBUTTONDOWN {
        if let Some(ctx) = HOOK_CTX.get() {
            let ms = &*(lparam.0 as *const MSLLHOOKSTRUCT);
            let xbutton = (ms.mouseData >> 16) & 0xFFFF;
            let vk = if xbutton == 1 { 0x05 } else { 0x06 };
            if vk == ctx.vk_mute.load(Ordering::Relaxed)
                || vk == ctx.vk_mute_2.load(Ordering::Relaxed)
            {
                let _ = ctx.tx.send(HotkeyAction::ToggleMute);
            } else if vk == ctx.vk_monitor.load(Ordering::Relaxed) {
                let _ = ctx.tx.send(HotkeyAction::TriggerMonitor);
            }
        }
    }
    CallNextHookEx(None, code, wparam, lparam)
}

fn map_calc_vk(vk: u32, flags: u32, shift: bool) -> Option<String> {
    let extended = (flags & 0x01) != 0;
    match vk {
        96..=105 => Some((vk - 96).to_string()),
        106 => Some("*".to_string()),
        107 => Some("+".to_string()),
        109 => Some("-".to_string()),
        110 | 188 | 190 => Some(".".to_string()),
        111 => Some("/".to_string()),
        v if v == VK_RETURN.0 as u32 && extended => Some("enter".to_string()),
        v if v == VK_BACK.0 as u32 => Some("backspace".to_string()),
        v if v == VK_DELETE.0 as u32 => Some("delete".to_string()),
        // Shift+8 / Shift+9 on EN or Shift+9 / Shift+0
        0x38 if shift => Some("(".to_string()),
        0x39 if shift => Some("(".to_string()),
        0x30 if shift => Some(")".to_string()),
        _ => None,
    }
}
