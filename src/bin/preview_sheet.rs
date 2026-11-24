use chrono::Local;
use image::{ImageBuffer, Rgba, RgbaImage};
use oled_customizer::oled::canvas::{Canvas128x40, OLED_HEIGHT, OLED_WIDTH};
use oled_customizer::oled::icons::*;
use oled_customizer::oled::views::{
    calculator::CalculatorView,
    clock::{render_clock_at, ClockStyle, ClockViewOpts},
    hw_monitor::{render_hw, HwStats, HwStyle},
    player::{MediaSource, PlayerStyle, PlayerView, SPECTRUM_BANDS},
    volume::render_volume,
};

fn blit_oled(
    sheet: &mut RgbaImage,
    canvas: &Canvas128x40,
    ox: u32,
    oy: u32,
    scale: u32,
    tint: [u8; 3],
) {
    // Sleek dark bezel border around the 128x40 OLED
    let bw = OLED_WIDTH as u32 * scale + 8;
    let bh = OLED_HEIGHT as u32 * scale + 8;
    for y in 0..bh {
        for x in 0..bw {
            let is_border = x == 0 || y == 0 || x == bw - 1 || y == bh - 1;
            let c = if is_border {
                Rgba([45, 58, 78, 255])
            } else {
                Rgba([8, 10, 14, 255])
            };
            sheet.put_pixel(ox + x, oy + y, c);
        }
    }

    for py in 0..OLED_HEIGHT {
        for px in 0..OLED_WIDTH {
            let c = if canvas.get_pixel(px, py) {
                Rgba([tint[0], tint[1], tint[2], 255])
            } else {
                Rgba([8, 10, 14, 255])
            };
            for sy in 0..scale {
                for sx in 0..scale {
                    sheet.put_pixel(
                        ox + 4 + (px as u32) * scale + sx,
                        oy + 4 + (py as u32) * scale + sy,
                        c,
                    );
                }
            }
        }
    }
}

fn blit_icon_zoom(sheet: &mut RgbaImage, rows: &[&str], ox: u32, oy: u32, scale: u32, tint: [u8; 3]) {
    let h = rows.len() as u32;
    let w = rows.first().map(|r| r.len()).unwrap_or(0) as u32;
    let pad = 6;
    for y in 0..(h * scale + pad * 2) {
        for x in 0..(w * scale + pad * 2) {
            let border = x == 0 || y == 0 || x == w * scale + pad * 2 - 1 || y == h * scale + pad * 2 - 1;
            sheet.put_pixel(
                ox + x,
                oy + y,
                if border {
                    Rgba([42, 52, 68, 255])
                } else {
                    Rgba([14, 17, 24, 255])
                },
            );
        }
    }
    for (ry, row) in rows.iter().enumerate() {
        for (rx, ch) in row.bytes().enumerate() {
            if ch == b'#' {
                for sy in 0..scale {
                    for sx in 0..scale {
                        sheet.put_pixel(
                            ox + pad + (rx as u32) * scale + sx,
                            oy + pad + (ry as u32) * scale + sy,
                            Rgba([tint[0], tint[1], tint[2], 255]),
                        );
                    }
                }
            }
        }
    }
}

fn main() {
    let scale = 3u32;
    let cell_w = OLED_WIDTH as u32 * scale + 28;
    let cell_h = OLED_HEIGHT as u32 * scale + 24;
    let cols = 3u32;
    let rows = 6u32;
    let width = cols * cell_w + 40;
    let height = rows * cell_h + 150;

    let mut sheet: RgbaImage = ImageBuffer::from_pixel(width, height, Rgba([13, 15, 20, 255]));
    let mut canvas = Canvas128x40::new();
    let now = Local::now();

    let white = [242, 248, 255];
    let cyan = [56, 242, 209];

    let mut idx = 0u32;
    let mut place = |c: &Canvas128x40, tint: [u8; 3]| {
        let col = idx % cols;
        let row = idx / cols;
        blit_oled(&mut sheet, c, 20 + col * cell_w, 20 + row * cell_h, scale, tint);
        idx += 1;
    };

    // 6 Clock styles
    for st in ClockStyle::ALL.iter() {
        let (battery_pct, show_battery_percent) = match st {
            ClockStyle::CleanDigital => (Some(78), true),
            ClockStyle::SplitTech => (Some(78), false),
            ClockStyle::RightCalendar => (Some(91), true),
            _ => (None, false),
        };
        render_clock_at(
            &mut canvas,
            &ClockViewOpts {
                style: *st,
                use_24h: true,
                display_seconds: true,
                use_turkish_days: false,
                battery_pct,
                show_battery_percent,
            },
            now,
        );
        place(&canvas, white);
    }

    // 5 Player styles
    let mut player = PlayerView::default();
    let sources = [
        (MediaSource::Generic, "Midnight City", "M83"),
        (MediaSource::YouTube, "Lo-Fi Synthwave Radio 24/7", "ChilledCow"),
        (MediaSource::Spotify, "Starlight (Extended Mix)", "Muse"),
        (MediaSource::Spotify, "Blinding Lights", "The Weeknd"),
        (MediaSource::YouTube, "Cyberpunk 2077 OST - V", "Marcin Przybylowicz"),
    ];
    let sample_bands: [f32; SPECTRUM_BANDS] = [
        0.85, 0.72, 0.92, 0.65, 0.50, 0.78, 0.88, 0.60, 0.42, 0.55,
        0.74, 0.82, 0.68, 0.48, 0.36, 0.52, 0.64, 0.40, 0.28, 0.20,
    ];
    let sample_peaks: [f32; SPECTRUM_BANDS] = [
        0.95, 0.84, 0.98, 0.78, 0.68, 0.88, 0.96, 0.75, 0.58, 0.66,
        0.82, 0.90, 0.78, 0.62, 0.50, 0.64, 0.76, 0.54, 0.42, 0.32,
    ];
    player.set_spectrum(sample_bands, sample_peaks);
    for (i, st) in PlayerStyle::ALL.iter().enumerate() {
        let (src, title, artist) = sources[i];
        player.update_track(title, artist, 84_000, 215_000, false, src);
        player.step = 18;
        player.render(&mut canvas, *st);
        place(&canvas, white);
    }

    // 3 HW styles
    let hw = HwStats {
        cpu_temp_c: Some(56),
        cpu_load_pct: 38,
        gpu_name: "RTX 5070 Ti".to_string(),
        gpu_temp_c: Some(62),
        gpu_load_pct: Some(84),
        ram_used_gb: 18.4,
        ram_total_gb: 64.0,
        ram_pct: 29,
        fps: Some(144),
        show_fps: true,
        fps_status: "Active".to_string(),
    };
    for st in HwStyle::ALL {
        render_hw(&mut canvas, &hw, st);
        place(&canvas, white);
    }

    // 2 Volume overlays (active + mic muted)
    render_volume(&mut canvas, 72, false, Some(false));
    place(&canvas, cyan);
    render_volume(&mut canvas, 35, false, Some(true));
    place(&canvas, white);

    // Calculator
    let mut calc = CalculatorView::new();
    calc.set_demo_state("(128+40)*2 =", "336");
    calc.render(&mut canvas);
    place(&canvas, white);

    // Bottom strip: zoomed 5x icons
    let icons_y = rows * cell_h + 36;
    let icons: &[&[&str]] = &[
        ICON_CPU,
        ICON_GPU,
        ICON_RAM,
        ICON_SPEAKER_HIGH,
        ICON_SPEAKER_MID,
        ICON_SPEAKER_LOW,
        ICON_SPEAKER_MUTE,
        ICON_MIC_ON,
        ICON_MIC_OFF,
        ICON_SPOTIFY_18,
        ICON_YOUTUBE_18,
        ICON_MEDIA_18,
    ];
    let mut ix = 20u32;
    for ic in icons {
        blit_icon_zoom(&mut sheet, ic, ix, icons_y, 5, cyan);
        let iw = ic.first().map(|r| r.len()).unwrap_or(12) as u32 * 5 + 22;
        ix += iw;
    }

    sheet
        .save("preview_sheet.png")
        .expect("save preview_sheet.png");
    println!("Saved preview_sheet.png ({width}x{height})");
}
