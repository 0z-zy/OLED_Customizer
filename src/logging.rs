use std::collections::VecDeque;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use chrono::Local;
use log::{Level, LevelFilter, Log, Metadata, Record};

use crate::config::app_data_dir;

const MAX_LOG_BYTES: u64 = 2 * 1024 * 1024;

struct RingLogger {
    ring: Arc<Mutex<VecDeque<String>>>,
    file: Mutex<Option<File>>,
    log_path: PathBuf,
    old_path: PathBuf,
    written_bytes: AtomicU64,
}

impl Log for RingLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        if metadata.level() <= Level::Warn {
            return true;
        }
        metadata.level() <= Level::Debug && metadata.target().starts_with("oled_customizer")
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let line = format!(
            "[{}] [{}] {}",
            Local::now().format("%H:%M:%S"),
            record.level(),
            record.args()
        );
        if let Ok(mut q) = self.ring.lock() {
            if q.len() >= 300 {
                q.pop_front();
            }
            q.push_back(line.clone());
        }
        if let Ok(mut f) = self.file.lock() {
            let line_len = (line.len() + 1) as u64;
            let total = self.written_bytes.fetch_add(line_len, Ordering::Relaxed) + line_len;
            if total >= MAX_LOG_BYTES {
                // Close current file handle, rotate to .old, and open a fresh log
                *f = None;
                let _ = fs::rename(&self.log_path, &self.old_path);
                *f = OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&self.log_path)
                    .ok();
                self.written_bytes.store(line_len, Ordering::Relaxed);
            }
            if let Some(ref mut file) = *f {
                let _ = writeln!(file, "{}", line);
            }
        }
    }

    fn flush(&self) {
        if let Ok(mut f) = self.file.lock() {
            if let Some(ref mut file) = *f {
                let _ = file.flush();
            }
        }
    }
}

static LOG_RING: OnceLock<Arc<Mutex<VecDeque<String>>>> = OnceLock::new();

pub fn init_logging(debug: bool) {
    let ring = LOG_RING
        .get_or_init(|| Arc::new(Mutex::new(VecDeque::with_capacity(300))))
        .clone();

    let dir = app_data_dir();
    let _ = fs::create_dir_all(&dir);
    let log_path = dir.join("debug.log");
    let old_path = dir.join("debug.log.old");

    let mut initial_len = fs::metadata(&log_path).map(|m| m.len()).unwrap_or(0);
    if initial_len > MAX_LOG_BYTES {
        let _ = fs::rename(&log_path, &old_path);
        initial_len = 0;
    }

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    let logger = Box::new(RingLogger {
        ring,
        file: Mutex::new(file),
        log_path,
        old_path,
        written_bytes: AtomicU64::new(initial_len),
    });

    let _ = log::set_boxed_logger(logger);
    log::set_max_level(if debug {
        LevelFilter::Debug
    } else {
        LevelFilter::Info
    });
}

pub fn set_debug_enabled(debug: bool) {
    log::set_max_level(if debug {
        LevelFilter::Debug
    } else {
        LevelFilter::Info
    });
}

pub fn recent_logs() -> Vec<String> {
    if let Some(ring) = LOG_RING.get() {
        if let Ok(q) = ring.lock() {
            return q.iter().cloned().collect();
        }
    }
    Vec::new()
}
