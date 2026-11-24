use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::process::CommandExt;
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::OnceLock;
use std::time::Instant;

use libloading::Library;

const TASK_NAME: &str = "OLED Customizer";
const LEGACY_V2_TASK_NAME: &str = "OLED Customizer v2";
const CREATE_NO_WINDOW: u32 = 0x08000000;
const STARTUP_CACHE_TTL_MS: u64 = 10_000;

static STARTUP_EPOCH: OnceLock<Instant> = OnceLock::new();
static STARTUP_CACHE_MS: AtomicU64 = AtomicU64::new(0);
static STARTUP_CACHE_VAL: AtomicBool = AtomicBool::new(false);

pub fn is_running_as_admin() -> bool {
    unsafe {
        if let Ok(lib) = Library::new("shell32.dll") {
            if let Ok(func) = lib.get::<unsafe extern "system" fn() -> i32>(b"IsUserAnAdmin\0") {
                return func() != 0;
            }
        }
    }
    false
}

pub fn invalidate_startup_cache() {
    STARTUP_CACHE_MS.store(0, Ordering::Relaxed);
}

fn query_startup_enabled_uncached() -> bool {
    Command::new("schtasks")
        .args(["/query", "/tn", TASK_NAME])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

pub fn is_startup_enabled() -> bool {
    let epoch = STARTUP_EPOCH.get_or_init(Instant::now);
    let now_ms = (epoch.elapsed().as_millis() as u64).saturating_add(1);
    let cached_ms = STARTUP_CACHE_MS.load(Ordering::Relaxed);
    if cached_ms != 0 && now_ms.saturating_sub(cached_ms) < STARTUP_CACHE_TTL_MS {
        return STARTUP_CACHE_VAL.load(Ordering::Relaxed);
    }
    let val = query_startup_enabled_uncached();
    STARTUP_CACHE_VAL.store(val, Ordering::Relaxed);
    STARTUP_CACHE_MS.store(now_ms, Ordering::Relaxed);
    val
}

pub fn set_startup_enabled(enable: bool, start_minimized: bool) -> Result<(), String> {
    if enable {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let exe_str = exe.display().to_string().replace('\'', "''");
        let dir_str = exe
            .parent()
            .map(|p| p.display().to_string().replace('\'', "''"))
            .unwrap_or_default();
        let arg_part = if start_minimized {
            "-Argument '--minimized'"
        } else {
            ""
        };
        let dir_part = if dir_str.is_empty() {
            String::new()
        } else {
            format!("-WorkingDirectory '{dir_str}'")
        };
        let ps_cmd = format!(
            "$action = New-ScheduledTaskAction -Execute '{exe_str}' {arg_part} {dir_part}; \
             $trigger = New-ScheduledTaskTrigger -AtLogon; \
             $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0; \
             Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force"
        );
        let out = Command::new("powershell")
            .args(["-NoProfile", "-Command", &ps_cmd])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| e.to_string())?;
        invalidate_startup_cache();
        if out.status.success() {
            // Remove older prototype task if present so only one task runs at logon
            let _ = Command::new("schtasks")
                .args(["/delete", "/tn", LEGACY_V2_TASK_NAME, "/f"])
                .creation_flags(CREATE_NO_WINDOW)
                .output();
            Ok(())
        } else {
            Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
        }
    } else {
        let out = Command::new("schtasks")
            .args(["/delete", "/tn", TASK_NAME, "/f"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| e.to_string())?;
        invalidate_startup_cache();
        if out.status.success() {
            // Remove older prototype task if present so only one task runs at logon
            let _ = Command::new("schtasks")
                .args(["/delete", "/tn", LEGACY_V2_TASK_NAME, "/f"])
                .creation_flags(CREATE_NO_WINDOW)
                .output();
            Ok(())
        } else {
            Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
        }
    }
}

fn decode_schtasks_xml(bytes: &[u8]) -> String {
    if bytes.contains(&0) {
        let mut units: Vec<u16> = bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect();
        if units.first() == Some(&0xFEFF) {
            units.remove(0);
        }
        String::from_utf16_lossy(&units)
    } else {
        String::from_utf8_lossy(bytes).into_owned()
    }
}

pub fn sync_startup_task_path_if_needed() {
    let Ok(exe) = std::env::current_exe() else {
        return;
    };
    let Ok(out) = Command::new("schtasks")
        .args(["/query", "/tn", TASK_NAME, "/xml"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    else {
        return;
    };
    if !out.status.success() {
        return;
    }

    let xml = decode_schtasks_xml(&out.stdout);
    let Some(start) = xml.find("<Command>").map(|i| i + "<Command>".len()) else {
        return;
    };
    let Some(rel_end) = xml[start..].find("</Command>") else {
        return;
    };
    let task_cmd = xml[start..start + rel_end].trim().trim_matches('"');
    let exe_str = exe.display().to_string();
    if !task_cmd.eq_ignore_ascii_case(&exe_str) {
        log::info!("Updating Task Scheduler path to {}", exe_str);
        let _ = set_startup_enabled(true, true);
    }
}

fn to_wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}

pub fn relaunch_as_admin(args: &str) -> bool {
    let Ok(exe) = std::env::current_exe() else {
        return false;
    };
    let dir = exe
        .parent()
        .map(|p| p.display().to_string())
        .unwrap_or_default();

    let op_w = to_wide("runas");
    let file_w = to_wide(&exe.display().to_string());
    let args_w = to_wide(args);
    let dir_w = to_wide(&dir);

    unsafe {
        if let Ok(lib) = Library::new("shell32.dll") {
            type FnShellExecuteW = unsafe extern "system" fn(
                isize,
                *const u16,
                *const u16,
                *const u16,
                *const u16,
                i32,
            ) -> isize;
            if let Ok(func) = lib.get::<FnShellExecuteW>(b"ShellExecuteW\0") {
                let ret = func(
                    0,
                    op_w.as_ptr(),
                    file_w.as_ptr(),
                    if args.is_empty() { std::ptr::null() } else { args_w.as_ptr() },
                    dir_w.as_ptr(),
                    1,
                );
                return ret > 32;
            }
        }
    }
    false
}
