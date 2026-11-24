use std::fs;
use std::path::PathBuf;
use std::sync::mpsc::{self, SyncSender};
use std::thread;
use std::time::{Duration, Instant};

const FALLBACK_PALETTE: [&str; 5] = ["#141926", "#1c2541", "#2d3a54", "#415a77", "#778da9"];

pub fn extract_dominant_colors(img_bytes: &[u8], count: usize) -> Vec<String> {
    let Ok(img) = image::load_from_memory(img_bytes) else {
        return FALLBACK_PALETTE.iter().map(|s| (*s).to_string()).collect();
    };
    let small = img
        .resize_exact(64, 64, image::imageops::FilterType::Triangle)
        .to_rgb8();
    const BINS: usize = 36;
    let mut bins: Vec<Vec<(f32, f32, f32)>> = vec![Vec::new(); BINS];
    let mut grays: Vec<(u8, u8, u8, f32)> = Vec::new();

    for px in small.pixels() {
        let [r, g, b] = px.0;
        let rf = r as f32 / 255.0;
        let gf = g as f32 / 255.0;
        let bf = b as f32 / 255.0;
        let max = rf.max(gf).max(bf);
        if max < 0.14 {
            continue;
        }
        let min = rf.min(gf).min(bf);
        let d = max - min;
        let s = if max > 0.0 { d / max } else { 0.0 };
        let h = if d == 0.0 {
            0.0
        } else if max == rf {
            ((gf - bf) / d).rem_euclid(6.0) / 6.0
        } else if max == gf {
            ((bf - rf) / d + 2.0) / 6.0
        } else {
            ((rf - gf) / d + 4.0) / 6.0
        };

        if s < 0.20 {
            grays.push((r, g, b, max));
        } else {
            let idx = ((h * BINS as f32) as usize) % BINS;
            bins[idx].push((h, s, max));
        }
    }

    let total_colored: usize = bins.iter().map(|b| b.len()).sum();
    let total_visible = grays.len() + total_colored;
    let is_mono = total_colored < 40
        || (total_visible > 0 && (total_colored as f32 / total_visible as f32) < 0.06);

    let mut picked: Vec<(f32, f32, f32)> = Vec::new();
    if !is_mono {
        let min_bin = (total_visible as f32 * 0.015).max(10.0) as usize;
        let mut candidates: Vec<(f32, f32, f32, f32)> = Vec::new();
        for b in &bins {
            if b.len() < min_bin {
                continue;
            }
            let len = b.len() as f32;
            let avg_h = b.iter().map(|p| p.0).sum::<f32>() / len;
            let avg_s = b.iter().map(|p| p.1).sum::<f32>() / len;
            let avg_v = b.iter().map(|p| p.2).sum::<f32>() / len;
            let score = len.sqrt() * avg_s.powf(1.2) * avg_v.powf(0.8);
            candidates.push((score, avg_h, avg_s, avg_v));
        }
        candidates.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        for (_, h, s, v) in candidates {
            let ok = picked.iter().all(|p| {
                let mut d = (h - p.0).abs();
                if d > 0.5 {
                    d = 1.0 - d;
                }
                d * 360.0 >= 28.0
            });
            if ok {
                picked.push((h, s, v));
                if picked.len() >= count {
                    break;
                }
            }
        }
    }

    if picked.is_empty() {
        if grays.is_empty() {
            return vec![
                "#f0f0f0".into(),
                "#b0b0b0".into(),
                "#707070".into(),
                "#404040".into(),
                "#202020".into(),
            ];
        }
        grays.sort_by(|a, b| b.3.partial_cmp(&a.3).unwrap_or(std::cmp::Ordering::Equal));
        return [0.05, 0.25, 0.50, 0.75, 0.95]
            .iter()
            .take(count)
            .map(|p| {
                let idx = (p * (grays.len() - 1) as f32) as usize;
                let (r, g, b, _) = grays[idx];
                format!("#{:02x}{:02x}{:02x}", r, g, b)
            })
            .collect();
    }

    let mut out = Vec::new();
    if picked.len() == 1 {
        let (h, _, _) = picked[0];
        let variations = [
            (0.0_f32, 0.96_f32, 1.0_f32),
            (0.035, 0.90, 0.90),
            (-0.035, 0.92, 0.80),
            (0.06, 0.85, 0.65),
            (-0.06, 0.95, 0.50),
        ];
        for (dh, s, v) in variations.into_iter().take(count) {
            let (r, g, b) = hsv_to_rgb((h + dh).rem_euclid(1.0), s, v);
            out.push(format!("#{:02x}{:02x}{:02x}", r, g, b));
        }
        return out;
    }

    for (h, s, v) in picked {
        let (r, g, b) = hsv_to_rgb(h, s.max(0.85), v.clamp(0.45, 1.0));
        out.push(format!("#{:02x}{:02x}{:02x}", r, g, b));
    }
    while out.len() < count {
        if let Some(first) = out.first().cloned() {
            out.push(first);
        } else {
            break;
        }
    }
    out
}

fn hsv_to_rgb(h: f32, s: f32, v: f32) -> (u8, u8, u8) {
    let i = (h * 6.0).floor() as i32;
    let f = h * 6.0 - i as f32;
    let p = v * (1.0 - s);
    let q = v * (1.0 - f * s);
    let t = v * (1.0 - (1.0 - f) * s);
    let (r, g, b) = match i.rem_euclid(6) {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, q, v),
        4 => (t, p, v),
        _ => (v, p, q),
    };
    (
        (r * 255.0).round() as u8,
        (g * 255.0).round() as u8,
        (b * 255.0).round() as u8,
    )
}

pub fn percent_encode(s: &str) -> String {
    const HEX: &[u8; 16] = b"0123456789ABCDEF";
    let mut out = String::with_capacity(s.len());
    for &b in s.as_bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~') {
            out.push(b as char);
        } else {
            out.push('%');
            out.push(HEX[(b >> 4) as usize] as char);
            out.push(HEX[(b & 0x0F) as usize] as char);
        }
    }
    out
}

pub fn safe_text(text: &str, max_len: usize) -> String {
    if text.is_empty() {
        return "?".to_string();
    }
    let cleaned: String = text
        .trim()
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_') {
                ch
            } else {
                '_'
            }
        })
        .take(max_len)
        .collect();
    let trimmed = cleaned.trim_matches('_');
    if trimmed.is_empty() {
        "?".to_string()
    } else {
        trimmed.to_string()
    }
}

pub fn build_event(
    playing: bool,
    colors: &[String],
    title: &str,
    include_title: bool,
    image_slot: Option<u8>,
) -> String {
    let mut hex_colors: Vec<String> = colors
        .iter()
        .take(5)
        .filter_map(|c| {
            let h = c.trim_start_matches('#').to_ascii_lowercase();
            (h.len() == 6).then_some(h)
        })
        .collect();

    while hex_colors.len() < 5 {
        if let Some(last) = hex_colors.last().cloned() {
            hex_colors.push(last);
        } else {
            let idx = hex_colors.len();
            hex_colors.push(FALLBACK_PALETTE[idx].trim_start_matches('#').to_string());
        }
    }

    let p_val = if playing { '1' } else { '0' };
    let t_val = if include_title {
        safe_text(title, 32)
    } else {
        "?".to_string()
    };

    let mut event = format!("p.{}|c.{}|t.{}", p_val, hex_colors.concat(), t_val);
    if let Some(slot) = image_slot {
        event.push_str(&format!("|i.{}", slot));
    }
    event
}

fn save_cover_images(raw_bytes: &[u8], slot: u8) {
    let Ok(local_app) = std::env::var("LOCALAPPDATA") else {
        return;
    };
    let vortx = PathBuf::from(local_app).join("VortxEngine");
    let Ok(entries) = fs::read_dir(&vortx) else {
        return;
    };
    for entry in entries.flatten() {
        let dyn_dir = entry
            .path()
            .join("Signal-x64")
            .join("Effects")
            .join("Dynamic");
        if dyn_dir.is_dir() {
            let _ = fs::write(dyn_dir.join("current_cover.jpg"), raw_bytes);
            let _ = fs::write(dyn_dir.join(format!("cover_{}.jpg", slot)), raw_bytes);
        }
    }
}

pub struct SignalRgbClient {
    tx: SyncSender<String>,
    last_push: Instant,
    last_delivered: String,
    last_track_key: String,
    had_cover_for_track: bool,
    img_slot: u8,
}

impl SignalRgbClient {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::sync_channel::<String>(4);
        let _ = thread::Builder::new()
            .name("SignalRGB-Pusher".to_string())
            .spawn(move || {
                let agent = ureq::AgentBuilder::new()
                    .timeout_connect(Duration::from_millis(500))
                    .timeout_read(Duration::from_millis(1000))
                    .build();
                let mut logged_ok = false;
                while let Ok(url) = rx.recv() {
                    match agent.post(&url).send_bytes(&[]) {
                        Ok(_) => {
                            if !logged_ok {
                                logged_ok = true;
                                log::info!("SignalRGB Pusher connected to Canvas API");
                            }
                        }
                        Err(e) => {
                            logged_ok = false;
                            log::debug!("SignalRGB push failed: {}", e);
                        }
                    }
                }
            });

        Self {
            tx,
            last_push: Instant::now() - Duration::from_secs(60),
            last_delivered: String::new(),
            last_track_key: String::new(),
            had_cover_for_track: false,
            img_slot: 1,
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn maybe_push(
        &mut self,
        enabled: bool,
        port: u16,
        sender: &str,
        include_title: bool,
        playing: bool,
        title: &str,
        artist: &str,
        album: &str,
        cover_bytes: Option<&[u8]>,
        colors: &[String],
    ) {
        if !enabled {
            return;
        }

        let track_key = format!("{}|{}|{}", title, artist, album);
        if track_key != self.last_track_key {
            self.last_track_key = track_key;
            self.img_slot = if self.img_slot == 1 { 2 } else { 1 };
            if let Some(bytes) = cover_bytes {
                self.had_cover_for_track = true;
                save_cover_images(bytes, self.img_slot);
            } else {
                self.had_cover_for_track = false;
            }
        } else if let Some(bytes) = cover_bytes {
            if !self.had_cover_for_track {
                self.had_cover_for_track = true;
                save_cover_images(bytes, self.img_slot);
            }
        }

        let slot = cover_bytes.map(|_| self.img_slot);
        let event = build_event(playing, colors, title, include_title, slot);
        let due_heartbeat = self.last_push.elapsed() >= Duration::from_secs(6);
        if event == self.last_delivered && !due_heartbeat {
            return;
        }
        self.last_delivered = event.clone();
        self.last_push = Instant::now();

        let url = format!(
            "http://127.0.0.1:{}/canvas/event?sender={}&event={}",
            port,
            percent_encode(sender),
            percent_encode(&event)
        );
        let _ = self.tx.try_send(url);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wire_event_matches_signalrgb_protocol() {
        let colors = vec![
            "#FF00AA".to_string(),
            "#00FF88".to_string(),
            "#112233".to_string(),
            "#445566".to_string(),
            "#778899".to_string(),
        ];
        let ev = build_event(true, &colors, "Midnight City!", true, Some(1));
        assert_eq!(
            ev,
            "p.1|c.ff00aa00ff88112233445566778899|t.Midnight_City|i.1"
        );
        assert_eq!(
            percent_encode("Media Ambience|p.1"),
            "Media%20Ambience%7Cp.1"
        );
        assert_eq!(safe_text("   ", 32), "?");
    }
}
