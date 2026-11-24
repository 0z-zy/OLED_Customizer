use serde::{Deserialize, Serialize};

use super::super::canvas::{Canvas128x40, Rect, OLED_WIDTH};
use super::super::fonts::{draw_font_clipped, measure_ttf, AlignH, TtfFontId};
use super::super::icons::{ICON_CPU, ICON_GPU, ICON_RAM};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum HwStyle {
    ThreeColumn,
    MeterBars,
    CompactSplit,
}

impl Default for HwStyle {
    fn default() -> Self {
        Self::ThreeColumn
    }
}

impl HwStyle {
    pub const ALL: [HwStyle; 3] = [
        HwStyle::ThreeColumn,
        HwStyle::MeterBars,
        HwStyle::CompactSplit,
    ];

    pub fn label(self) -> &'static str {
        match self {
            HwStyle::ThreeColumn => "3-Column Tech",
            HwStyle::MeterBars => "Meter Bars",
            HwStyle::CompactSplit => "Compact Split",
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct HwStats {
    pub cpu_temp_c: Option<i32>,
    pub cpu_load_pct: u8,
    pub gpu_name: String,
    pub gpu_temp_c: Option<i32>,
    pub gpu_load_pct: Option<u8>,
    pub ram_used_gb: f32,
    pub ram_total_gb: f32,
    pub ram_pct: u8,
    pub fps: Option<u32>,
    pub show_fps: bool,
    pub fps_status: String,
}

fn draw_meter_bar(canvas: &mut Canvas128x40, x: i32, y: i32, w: i32, h: i32, pct: u8) {
    canvas.draw_rounded_rect(x, y, w, h, true);
    let inner_w = ((w - 4) as f32 * (pct.min(100) as f32 / 100.0)).round() as i32;
    if inner_w > 0 {
        canvas.fill_rect(x + 2, y + 2, inner_w, (h - 4).max(1), true);
    }
}

pub fn render_hw(canvas: &mut Canvas128x40, stats: &HwStats, style: HwStyle) {
    canvas.clear();
    let clip = Rect::full();

    let cpu_t = stats
        .cpu_temp_c
        .map(|t| format!("{}°", t))
        .unwrap_or_else(|| "--".to_string());
    let gpu_t = stats
        .gpu_temp_c
        .map(|t| format!("{}°", t))
        .unwrap_or_else(|| "--".to_string());
    let gpu_l = format!("{}%", stats.gpu_load_pct.unwrap_or(0));
    let cpu_l = format!("{}%", stats.cpu_load_pct);
    let ram_u = format!("{:.1}G", stats.ram_used_gb);
    let ram_sub = if stats.show_fps {
        match stats.fps {
            Some(f) if f > 0 => format!("{} FPS", f),
            _ => "IDLE".to_string(),
        }
    } else {
        format!("{}GB", stats.ram_total_gb.round() as i32)
    };

    match style {
        HwStyle::ThreeColumn => {
            let col_w = OLED_WIDTH / 3;
            let centers = [col_w / 2, col_w + col_w / 2, col_w * 2 + col_w / 2];

            // Subtle dotted vertical dividers between columns
            for div_x in [col_w, col_w * 2] {
                for y in (4..36).step_by(3) {
                    canvas.set_pixel(div_x, y, true);
                }
            }

            // Column 1: CPU
            canvas.draw_bitmap(centers[0] - 6, 1, ICON_CPU, true);
            draw_font_clipped(canvas, TtfFontId::Verdana11, centers[0], 15, &cpu_t, AlignH::Center, true, clip);
            draw_font_clipped(canvas, TtfFontId::Verdana11, centers[0], 28, &cpu_l, AlignH::Center, true, clip);

            // Column 2: GPU
            canvas.draw_bitmap(centers[1] - 6, 1, ICON_GPU, true);
            draw_font_clipped(canvas, TtfFontId::Verdana11, centers[1], 15, &gpu_t, AlignH::Center, true, clip);
            draw_font_clipped(canvas, TtfFontId::Verdana11, centers[1], 28, &gpu_l, AlignH::Center, true, clip);

            // Column 3: RAM / FPS
            canvas.draw_bitmap(centers[2] - 6, 1, ICON_RAM, true);
            draw_font_clipped(canvas, TtfFontId::Verdana11, centers[2], 15, &ram_u, AlignH::Center, true, clip);
            let sub_font = if measure_ttf(TtfFontId::Verdana11, &ram_sub) > col_w - 2 {
                if measure_ttf(TtfFontId::Verdana9, &ram_sub) > col_w - 2 {
                    TtfFontId::Munro10
                } else {
                    TtfFontId::Verdana9
                }
            } else {
                TtfFontId::Verdana11
            };
            draw_font_clipped(canvas, sub_font, centers[2], 28, &ram_sub, AlignH::Center, true, clip);
        }

        HwStyle::MeterBars => {
            // 3 sleek horizontal dashboard rows
            let rows = [
                (1, ICON_CPU, cpu_t.clone(), stats.cpu_load_pct, cpu_l.clone()),
                (
                    14,
                    ICON_GPU,
                    gpu_t.clone(),
                    stats.gpu_load_pct.unwrap_or(0),
                    gpu_l.clone(),
                ),
                (27, ICON_RAM, ram_u.clone(), stats.ram_pct, ram_sub.clone()),
            ];

            for (y, icon, mid, pct, right) in rows {
                canvas.draw_bitmap(2, y, icon, true);
                draw_font_clipped(canvas, TtfFontId::Verdana9, 17, y + 2, &mid, AlignH::Left, true, clip);
                draw_meter_bar(canvas, 50, y + 2, 34, 8, pct);
                let rf = if measure_ttf(TtfFontId::Verdana9, &right) > 40 {
                    TtfFontId::Munro10
                } else {
                    TtfFontId::Verdana9
                };
                draw_font_clipped(
                    canvas,
                    rf,
                    OLED_WIDTH - 2,
                    y + 2,
                    &right,
                    AlignH::Right,
                    true,
                    clip,
                );
            }
        }

        HwStyle::CompactSplit => {
            // Left card (0..75): CPU + GPU stacked compact rows
            canvas.draw_rounded_rect(1, 1, 74, 38, true);

            canvas.draw_bitmap(4, 4, ICON_CPU, true);
            draw_font_clipped(canvas, TtfFontId::Verdana9, 19, 6, &cpu_t, AlignH::Left, true, clip);
            draw_font_clipped(canvas, TtfFontId::Verdana9, 71, 6, &cpu_l, AlignH::Right, true, clip);

            canvas.draw_hline(4, 71, 19, true);

            canvas.draw_bitmap(4, 22, ICON_GPU, true);
            draw_font_clipped(canvas, TtfFontId::Verdana9, 19, 24, &gpu_t, AlignH::Left, true, clip);
            draw_font_clipped(canvas, TtfFontId::Verdana9, 71, 24, &gpu_l, AlignH::Right, true, clip);

            // Right card (78..127): RAM + meter + FPS/total
            canvas.draw_rounded_rect(78, 1, 49, 38, true);
            canvas.draw_bitmap(81, 4, ICON_RAM, true);
            draw_font_clipped(canvas, TtfFontId::Munro10, 96, 7, &ram_u, AlignH::Left, true, clip);
            draw_meter_bar(canvas, 82, 18, 41, 7, stats.ram_pct);
            draw_font_clipped(canvas, TtfFontId::Munro10, 102, 29, &ram_sub, AlignH::Center, true, clip);
        }
    }
}
