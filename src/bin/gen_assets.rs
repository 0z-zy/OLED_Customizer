use std::fs;
use std::io::BufWriter;
use std::path::Path;

use image::{
    codecs::ico::{IcoEncoder, IcoFrame},
    imageops::FilterType,
    ExtendedColorType, ImageBuffer, Rgba, RgbaImage,
};
use oled_customizer::oled::icons::*;

fn blend(dst: &mut Rgba<u8>, src: [u8; 4]) {
    let sa = src[3] as f32 / 255.0;
    if sa <= 0.0 {
        return;
    }
    let da = dst[3] as f32 / 255.0;
    let out_a = sa + da * (1.0 - sa);
    if out_a <= 0.0 {
        return;
    }
    for i in 0..3 {
        let c = (src[i] as f32 * sa + dst[i] as f32 * da * (1.0 - sa)) / out_a;
        dst[i] = c.round().clamp(0.0, 255.0) as u8;
    }
    dst[3] = (out_a * 255.0).round().clamp(0.0, 255.0) as u8;
}

fn sdf_rounded_rect(x: f32, y: f32, cx: f32, cy: f32, hw: f32, hh: f32, r: f32) -> f32 {
    let dx = (x - cx).abs() - hw + r;
    let dy = (y - cy).abs() - hh + r;
    let outside = (dx.max(0.0).powi(2) + dy.max(0.0).powi(2)).sqrt();
    let inside = dx.max(dy).min(0.0);
    outside + inside - r
}

fn render_app_icon(size: u32, bold_small: bool) -> RgbaImage {
    let mut img: RgbaImage = ImageBuffer::new(size, size);
    let s = size as f32;
    let cx = s * 0.5;
    let cy = s * 0.5;

    let sq_half = s * 0.45;
    let sq_r = s * 0.14;

    // Inner chip / hardware frame
    let chip_half = s * 0.31;
    let chip_r = s * 0.065;

    // Sleek central OLED pulse bar / screen
    let scr_hw = s * 0.24;
    let scr_hh = s * 0.105;

    for y in 0..size {
        for x in 0..size {
            let fx = x as f32 + 0.5;
            let fy = y as f32 + 0.5;
            let d_sq = sdf_rounded_rect(fx, fy, cx, cy, sq_half, sq_half, sq_r);

            if d_sq <= 1.0 {
                let cov = (1.0 - d_sq).clamp(0.0, 1.0);
                let t = fy / s;
                let diag = ((fx + fy) / (2.0 * s)).clamp(0.0, 1.0);

                // Deep carbon-obsidian squircle with subtle top-left studio light
                let mut r = 12.0 + (1.0 - diag) * 10.0 + t * 4.0;
                let mut g = 16.0 + (1.0 - diag) * 14.0 + t * 6.0;
                let mut b = 24.0 + (1.0 - diag) * 20.0 + t * 8.0;

                // Crisp metallic rim
                if d_sq > -s * 0.020 {
                    let rim = 1.0 - ((d_sq + s * 0.010).abs() / (s * 0.011)).clamp(0.0, 1.0);
                    r += rim * 42.0;
                    g += rim * 54.0;
                    b += rim * 76.0;
                }

                // Ambient cyan-teal halo from center
                let dx = (fx - cx) / (s * 0.40);
                let dy = (fy - cy) / (s * 0.40);
                let glow = (1.0 - (dx * dx + dy * dy).sqrt()).max(0.0).powf(2.0);
                g += glow * 78.0;
                b += glow * 68.0;

                let mut px = Rgba([
                    r.clamp(0.0, 255.0) as u8,
                    g.clamp(0.0, 255.0) as u8,
                    b.clamp(0.0, 255.0) as u8,
                    (cov * 255.0) as u8,
                ]);

                // Microchip pins along top/bottom/left/right of the inner frame
                if !bold_small {
                    for i in [-2, -1, 0, 1, 2] {
                        let off = i as f32 * s * 0.088;
                        let pin_w = s * 0.018;
                        let pin_l = s * 0.055;
                        // Top & bottom pins
                        let d_tb = sdf_rounded_rect(fx, fy, cx + off, cy, pin_w, chip_half + pin_l, pin_w * 0.5);
                        if d_tb <= 0.6 && (fy - cy).abs() > chip_half - s * 0.01 {
                            let a = (1.0 - d_tb).clamp(0.0, 1.0);
                            blend(&mut px, [0, 212, 170, (a * 210.0) as u8]);
                        }
                        // Left & right pins
                        let d_lr = sdf_rounded_rect(fx, fy, cx, cy + off, chip_half + pin_l, pin_w, pin_w * 0.5);
                        if d_lr <= 0.6 && (fx - cx).abs() > chip_half - s * 0.01 {
                            let a = (1.0 - d_lr).clamp(0.0, 1.0);
                            blend(&mut px, [0, 212, 170, (a * 210.0) as u8]);
                        }
                    }
                }

                // Inner dark glass hardware die
                let d_chip = sdf_rounded_rect(fx, fy, cx, cy, chip_half, chip_half, chip_r);
                if d_chip <= 1.0 {
                    let ccov = (1.0 - d_chip).clamp(0.0, 1.0);
                    blend(&mut px, [7, 10, 15, (ccov * 245.0) as u8]);
                    let bw = (s * 0.018).max(1.4);
                    if d_chip > -bw {
                        let ba = (1.0 - (d_chip + bw * 0.5).abs() / (bw * 0.6)).clamp(0.0, 1.0);
                        blend(&mut px, [56, 242, 209, (ba * 240.0) as u8]);
                    }
                }

                // Central OLED screen pill + bold 5-bar telemetry waveform
                let d_scr = sdf_rounded_rect(fx, fy, cx, cy, scr_hw, scr_hh, s * 0.032);
                if d_scr <= 0.8 {
                    let sa = (1.0 - d_scr).clamp(0.0, 1.0);
                    blend(&mut px, [12, 22, 28, (sa * 235.0) as u8]);
                }

                let bar_heights: &[f32] = if bold_small {
                    &[0.065, 0.135, 0.090]
                } else {
                    &[0.055, 0.105, 0.155, 0.095, 0.065]
                };
                let n_bars = bar_heights.len() as f32;
                let spacing = s * if bold_small { 0.12 } else { 0.078 };
                let bar_hw = s * if bold_small { 0.038 } else { 0.023 };
                for (idx, bh) in bar_heights.iter().enumerate() {
                    let bx = cx + (idx as f32 - (n_bars - 1.0) * 0.5) * spacing;
                    let d_bar = sdf_rounded_rect(fx, fy, bx, cy, bar_hw, s * (*bh) * 0.5, bar_hw * 0.7);
                    if d_bar <= 0.7 {
                        let a = (1.0 - d_bar).clamp(0.0, 1.0);
                        let col = if idx == bar_heights.len() / 2 {
                            [235, 255, 252, (a * 255.0) as u8]
                        } else {
                            [0, 228, 188, (a * 255.0) as u8]
                        };
                        blend(&mut px, col);
                    }
                }

                img.put_pixel(x, y, px);
            }
        }
    }

    img
}

fn export_pixel_icon(path: &Path, rows: &[&str]) {
    let h = rows.len() as u32;
    let w = rows.first().map(|r| r.len()).unwrap_or(0) as u32;
    let mut img = RgbaImage::new(w, h);
    for (y, row) in rows.iter().enumerate() {
        for (x, ch) in row.bytes().enumerate() {
            let p = if ch == b'#' {
                Rgba([255, 255, 255, 255])
            } else {
                Rgba([0, 0, 0, 255])
            };
            img.put_pixel(x as u32, y as u32, p);
        }
    }
    img.save(path).expect("save pixel icon");
}

fn main() {
    let assets_dir = Path::new("assets");
    let icons_dir = assets_dir.join("icons");
    fs::create_dir_all(&icons_dir).expect("create icons dir");

    // 1. Render crisp 1024x1024 PNG (supersampled from 1024 directly, smooth SDF edges)
    let hi = render_app_icon(1024, false);
    hi.save(assets_dir.join("app_icon.png"))
        .expect("save app_icon.png");

    // 2. Build multi-resolution app_icon.ico
    let ico_sizes = [16u32, 24, 32, 48, 64, 128, 256];
    let mut frames = Vec::new();
    for sz in ico_sizes {
        let frame_img = if sz <= 24 {
            render_app_icon(sz * 4, true)
        } else {
            hi.clone()
        };
        let resized = image::imageops::resize(&frame_img, sz, sz, FilterType::Lanczos3);
        let raw = resized.into_raw();
        frames.push(IcoFrame::as_png(&raw, sz, sz, ExtendedColorType::Rgba8).expect("ico frame"));
    }
    let ico_file = fs::File::create(assets_dir.join("app_icon.ico")).expect("create app_icon.ico");
    let encoder = IcoEncoder::new(BufWriter::new(ico_file));
    encoder.encode_images(&frames).expect("encode ico");

    // 3. Export all redesigned 1-bit pixel icons
    export_pixel_icon(&icons_dir.join("cpu_icon.png"), ICON_CPU);
    export_pixel_icon(&icons_dir.join("gpu_icon.png"), ICON_GPU);
    export_pixel_icon(&icons_dir.join("ram_icon.png"), ICON_RAM);
    export_pixel_icon(&icons_dir.join("speaker_mute.png"), ICON_SPEAKER_MUTE);
    export_pixel_icon(&icons_dir.join("speaker_low.png"), ICON_SPEAKER_LOW);
    export_pixel_icon(&icons_dir.join("speaker_mid.png"), ICON_SPEAKER_MID);
    export_pixel_icon(&icons_dir.join("speaker_high.png"), ICON_SPEAKER_HIGH);
    export_pixel_icon(&icons_dir.join("mic_on.png"), ICON_MIC_ON);
    export_pixel_icon(&icons_dir.join("mic_off.png"), ICON_MIC_OFF);
    export_pixel_icon(&icons_dir.join("spotify-18.png"), ICON_SPOTIFY_18);
    export_pixel_icon(&icons_dir.join("youtube-18.png"), ICON_YOUTUBE_18);
    export_pixel_icon(&icons_dir.join("media-18.png"), ICON_MEDIA_18);

    println!("Generated assets/app_icon.png, assets/app_icon.ico, and 12 OLED icons.");
}
