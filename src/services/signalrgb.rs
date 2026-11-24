use std::time::{Duration, Instant};

use serde_json::json;

pub fn extract_dominant_colors(img_bytes: &[u8], count: usize) -> Vec<String> {
    let Ok(img) = image::load_from_memory(img_bytes) else {
        return vec![
            "#141926".into(),
            "#1c2541".into(),
            "#2d3a54".into(),
            "#415a77".into(),
            "#778da9".into(),
        ];
    };
    let small = img.resize_exact(64, 64, image::imageops::FilterType::Triangle).to_rgb8();
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
    let is_mono = total_colored < 40 || (total_visible > 0 && (total_colored as f32 / total_visible as f32) < 0.06);

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

pub struct SignalRgbClient {
    agent: ureq::Agent,
    last_push: Instant,
    last_sig: String,
}

impl SignalRgbClient {
    pub fn new() -> Self {
        Self {
            agent: ureq::AgentBuilder::new()
                .timeout_connect(Duration::from_millis(250))
                .timeout_read(Duration::from_millis(400))
                .build(),
            last_push: Instant::now() - Duration::from_secs(60),
            last_sig: String::new(),
        }
    }

    pub fn maybe_push(
        &mut self,
        enabled: bool,
        port: u16,
        sender: &str,
        include_title: bool,
        playing: bool,
        title: &str,
        colors: &[String],
    ) {
        if !enabled {
            return;
        }
        let sig = format!("{}:{}:{}", playing, title, colors.join(","));
        let due_heartbeat = self.last_push.elapsed() >= Duration::from_secs(6);
        if sig == self.last_sig && !due_heartbeat {
            return;
        }
        self.last_sig = sig;
        self.last_push = Instant::now();

        let url = format!("http://127.0.0.1:{}/canvas/event", port);
        let payload = json!({
            "sender": sender,
            "playing": playing,
            "title": if include_title { title } else { "" },
            "colors": colors,
        });
        let _ = self.agent.post(&url).send_json(payload);
    }
}
