use chrono::{Datelike, Local, Timelike};
use serde::{Deserialize, Serialize};

use super::super::canvas::{Canvas128x40, Rect, OLED_HEIGHT, OLED_WIDTH};
use super::super::fonts::{draw_font, draw_font_clipped, measure_ttf, AlignH, TtfFontId};
use super::super::icons::{draw_battery, draw_battery_inline};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ClockStyle {
    CleanDigital,
    BigBold,
    SplitTech,
    RightCalendar,
    ModernAnalog,
    MinimalPill,
}

impl Default for ClockStyle {
    fn default() -> Self {
        Self::CleanDigital
    }
}

impl ClockStyle {
    pub const ALL: [ClockStyle; 6] = [
        ClockStyle::CleanDigital,
        ClockStyle::BigBold,
        ClockStyle::SplitTech,
        ClockStyle::RightCalendar,
        ClockStyle::ModernAnalog,
        ClockStyle::MinimalPill,
    ];

    pub fn label(self) -> &'static str {
        match self {
            ClockStyle::CleanDigital => "Clean Digital",
            ClockStyle::BigBold => "Big Bold",
            ClockStyle::SplitTech => "Split Tech",
            ClockStyle::RightCalendar => "Right Calendar",
            ClockStyle::ModernAnalog => "Modern Analog",
            ClockStyle::MinimalPill => "Minimal Pill",
        }
    }
}

#[derive(Clone, Debug)]
pub struct ClockViewOpts {
    pub style: ClockStyle,
    pub use_24h: bool,
    pub display_seconds: bool,
    pub use_turkish_days: bool,
    pub battery_pct: Option<u8>,
    pub show_battery_percent: bool,
}

fn day_abbrev(weekday: chrono::Weekday, turkish: bool) -> &'static str {
    if turkish {
        match weekday {
            chrono::Weekday::Mon => "PZT",
            chrono::Weekday::Tue => "SAL",
            chrono::Weekday::Wed => "CAR",
            chrono::Weekday::Thu => "PER",
            chrono::Weekday::Fri => "CUM",
            chrono::Weekday::Sat => "CMT",
            chrono::Weekday::Sun => "PAZ",
        }
    } else {
        match weekday {
            chrono::Weekday::Mon => "MON",
            chrono::Weekday::Tue => "TUE",
            chrono::Weekday::Wed => "WED",
            chrono::Weekday::Thu => "THU",
            chrono::Weekday::Fri => "FRI",
            chrono::Weekday::Sat => "SAT",
            chrono::Weekday::Sun => "SUN",
        }
    }
}

fn month_abbrev(month: u32, turkish: bool) -> &'static str {
    if turkish {
        match month {
            1 => "OCA",
            2 => "SUB",
            3 => "MAR",
            4 => "NIS",
            5 => "MAY",
            6 => "HAZ",
            7 => "TEM",
            8 => "AGU",
            9 => "EYL",
            10 => "EKI",
            11 => "KAS",
            12 => "ARA",
            _ => "---",
        }
    } else {
        match month {
            1 => "JAN",
            2 => "FEB",
            3 => "MAR",
            4 => "APR",
            5 => "MAY",
            6 => "JUN",
            7 => "JUL",
            8 => "AUG",
            9 => "SEP",
            10 => "OCT",
            11 => "NOV",
            12 => "DEC",
            _ => "---",
        }
    }
}

pub fn render_clock(canvas: &mut Canvas128x40, opts: &ClockViewOpts) {
    let now = Local::now();
    render_clock_at(canvas, opts, now);
}

pub fn render_clock_at(
    canvas: &mut Canvas128x40,
    opts: &ClockViewOpts,
    now: chrono::DateTime<Local>,
) {
    canvas.clear();
    let clip = Rect::full();

    let h24 = now.hour();
    let (h_disp, am_pm) = if opts.use_24h {
        (h24, None)
    } else {
        let h12 = match h24 % 12 {
            0 => 12,
            v => v,
        };
        (h12, Some(if h24 < 12 { "AM" } else { "PM" }))
    };

    let hh_mm = format!("{:02}:{:02}", h_disp, now.minute());
    let sec_str = format!(":{:02}", now.second());
    let day = day_abbrev(now.weekday(), opts.use_turkish_days);
    let mon = month_abbrev(now.month(), opts.use_turkish_days);
    let date_full = format!("{} {:02}/{:02}/{:04}", day, now.day(), now.month(), now.year());

    match opts.style {
        ClockStyle::CleanDigital => {
            // Top DS-Digital time, sleek thin rule with end dots, crisp DS-Digital small date below
            let time_str = if opts.display_seconds {
                format!("{}{}", hh_mm, sec_str)
            } else {
                hh_mm.clone()
            };

            let center_x = if opts.battery_pct.is_some() { 50 } else { 64 };
            draw_font(
                canvas,
                TtfFontId::DigiBig,
                center_x,
                4,
                &time_str,
                AlignH::Center,
                true,
            );
            if !opts.display_seconds {
                if let Some(ap) = am_pm {
                    let tw = measure_ttf(TtfFontId::DigiBig, &time_str);
                    draw_font(
                        canvas,
                        TtfFontId::Munro10,
                        (center_x + tw / 2 + 7).min(102),
                        14,
                        ap,
                        AlignH::Center,
                        true,
                    );
                }
            }

            // Sleek hairline rule with 2px end caps
            canvas.draw_hline(12, 115, 23, true);
            canvas.fill_rect(10, 22, 2, 3, true);
            canvas.fill_rect(116, 22, 2, 3, true);

            draw_font_clipped(
                canvas,
                TtfFontId::DigiSmall,
                64,
                27,
                &date_full,
                AlignH::Center,
                true,
                clip,
            );
        }

        ClockStyle::BigBold => {
            let time_str = if opts.display_seconds {
                format!("{}{}", hh_mm, sec_str)
            } else {
                hh_mm.clone()
            };
            let cx = if opts.battery_pct.is_some() { 50 } else { 64 };
            let font = if opts.display_seconds {
                TtfFontId::DigiBig
            } else {
                TtfFontId::DigiHuge
            };
            let top_y = if opts.display_seconds { 12 } else { 8 };
            draw_font(canvas, font, cx, top_y, &time_str, AlignH::Center, true);

            if let Some(ap) = am_pm {
                let tw = measure_ttf(font, &time_str);
                let ap_x = (cx + tw / 2 + 8).min(120);
                draw_font(canvas, TtfFontId::Munro10, ap_x, 26, ap, AlignH::Center, true);
            }
        }

        ClockStyle::SplitTech => {
            // Left Calendar Card (34x34)
            canvas.draw_rounded_rect(3, 3, 34, 34, true);
            canvas.fill_rect(4, 4, 32, 10, true);
            // Inverted day header (black text on white bar)
            draw_font_clipped(canvas, TtfFontId::Verdana9, 20, 5, day, AlignH::Center, false, clip);

            let dom = format!("{:02}", now.day());
            draw_font_clipped(
                canvas,
                TtfFontId::Verdana11,
                20,
                21,
                &dom,
                AlignH::Center,
                true,
                clip,
            );

            // Right column: DS-Digital HH:MM(:SS) + Verdana Month/Year
            let right_cx = if opts.battery_pct.is_some() { 70 } else { 83 };
            let time_str = if opts.display_seconds {
                format!("{}{}", hh_mm, sec_str)
            } else {
                hh_mm.clone()
            };
            let font = if opts.display_seconds {
                TtfFontId::DigiMed
            } else {
                TtfFontId::DigiBig
            };
            let top_y = if opts.display_seconds { 11 } else { 8 };
            draw_font(canvas, font, right_cx, top_y, &time_str, AlignH::Center, true);

            let sub = if let Some(ap) = am_pm {
                format!("{} {} {}", mon, now.year(), ap)
            } else {
                format!("{} {:04}", mon, now.year())
            };
            draw_font_clipped(
                canvas,
                TtfFontId::Verdana9,
                right_cx,
                29,
                &sub,
                AlignH::Center,
                true,
                clip,
            );
        }

        ClockStyle::RightCalendar => {
            // Right Calendar Card (34x34 at x=92..125, y=3..36)
            canvas.draw_rounded_rect(92, 3, 34, 34, true);
            canvas.fill_rect(93, 4, 32, 10, true);
            draw_font_clipped(canvas, TtfFontId::Verdana9, 109, 5, day, AlignH::Center, false, clip);

            let dom = format!("{:02}", now.day());
            draw_font_clipped(
                canvas,
                TtfFontId::Verdana11,
                109,
                17,
                &dom,
                AlignH::Center,
                true,
                clip,
            );
            draw_font_clipped(canvas, TtfFontId::Munro10, 109, 29, mon, AlignH::Center, true, clip);

            // Top-Left Battery + Inline Percentage Strip (x=3..87, y=3..11)
            if let Some(pct) = opts.battery_pct {
                draw_battery_inline(canvas, 3, 3, pct, opts.show_battery_percent);
                let top_right = if let Some(ap) = am_pm {
                    ap.to_string()
                } else {
                    format!("{:04}", now.year())
                };
                draw_font_clipped(
                    canvas,
                    TtfFontId::Verdana9,
                    87,
                    4,
                    &top_right,
                    AlignH::Right,
                    true,
                    clip,
                );
            } else {
                let top_left = if let Some(ap) = am_pm {
                    format!("{} {:04} {}", mon, now.year(), ap)
                } else {
                    format!("{} {:04}", mon, now.year())
                };
                draw_font_clipped(
                    canvas,
                    TtfFontId::Verdana9,
                    3,
                    4,
                    &top_left,
                    AlignH::Left,
                    true,
                    clip,
                );
            }

            // Sleek horizontal divider
            canvas.draw_hline(3, 87, 14, true);

            // Bottom-Left Large DS-Digital Clock (y=20..34)
            let time_str = if opts.display_seconds {
                format!("{}{}", hh_mm, sec_str)
            } else {
                hh_mm.clone()
            };
            draw_font(canvas, TtfFontId::DigiBig, 45, 20, &time_str, AlignH::Center, true);
        }

        ClockStyle::ModernAnalog => {
            // Analog dial on the left, digital + date on the right
            let cx = 22;
            let cy = 20;
            let r = 17;
            canvas.draw_circle(cx, cy, r, true);
            // 12 hour tick marks
            for i in 0..12 {
                let ang = (i as f32) * 30.0_f32.to_radians() - std::f32::consts::FRAC_PI_2;
                let inner = if i % 3 == 0 { r - 4 } else { r - 2 };
                let x0 = cx as f32 + (inner as f32) * ang.cos();
                let y0 = cy as f32 + (inner as f32) * ang.sin();
                let x1 = cx as f32 + ((r - 1) as f32) * ang.cos();
                let y1 = cy as f32 + ((r - 1) as f32) * ang.sin();
                canvas.draw_line(
                    x0.round() as i32,
                    y0.round() as i32,
                    x1.round() as i32,
                    y1.round() as i32,
                    true,
                );
            }

            let h_ang = ((now.hour() % 12) as f32 + now.minute() as f32 / 60.0)
                * 30.0_f32.to_radians()
                - std::f32::consts::FRAC_PI_2;
            let m_ang = (now.minute() as f32) * 6.0_f32.to_radians() - std::f32::consts::FRAC_PI_2;
            let s_ang = (now.second() as f32) * 6.0_f32.to_radians() - std::f32::consts::FRAC_PI_2;

            // Hour hand (thick 2px feel)
            let hx = (cx as f32 + 9.0 * h_ang.cos()).round() as i32;
            let hy = (cy as f32 + 9.0 * h_ang.sin()).round() as i32;
            canvas.draw_line(cx, cy, hx, hy, true);
            canvas.draw_line(cx + 1, cy, hx + 1, hy, true);

            // Minute hand
            let mx = (cx as f32 + 13.0 * m_ang.cos()).round() as i32;
            let my = (cy as f32 + 13.0 * m_ang.sin()).round() as i32;
            canvas.draw_line(cx, cy, mx, my, true);

            // Second hand
            if opts.display_seconds {
                let sx = (cx as f32 + 14.0 * s_ang.cos()).round() as i32;
                let sy = (cy as f32 + 14.0 * s_ang.sin()).round() as i32;
                canvas.draw_line(cx, cy, sx, sy, true);
            }
            canvas.fill_circle(cx, cy, 1, true);

            // Right half: Digital time + Day + Date
            let rx = 46;
            draw_font(canvas, TtfFontId::DigiMed, rx, 8, &hh_mm, AlignH::Left, true);
            let date_short = format!("{} {:02}/{:02}", day, now.day(), now.month());
            draw_font_clipped(canvas, TtfFontId::DigiSmall, rx, 25, &date_short, AlignH::Left, true, clip);
        }

        ClockStyle::MinimalPill => {
            // Corner viewfinder brackets + centered sleek time + bottom seconds bar
            // Top-left & top-right brackets
            canvas.draw_hline(3, 10, 3, true);
            canvas.draw_vline(3, 3, 10, true);
            canvas.draw_hline(OLED_WIDTH - 11, OLED_WIDTH - 4, 3, true);
            canvas.draw_vline(OLED_WIDTH - 4, 3, 10, true);
            // Bottom-left & bottom-right brackets
            canvas.draw_hline(3, 10, OLED_HEIGHT - 6, true);
            canvas.draw_vline(3, OLED_HEIGHT - 13, OLED_HEIGHT - 6, true);
            canvas.draw_hline(OLED_WIDTH - 11, OLED_WIDTH - 4, OLED_HEIGHT - 6, true);
            canvas.draw_vline(OLED_WIDTH - 4, OLED_HEIGHT - 13, OLED_HEIGHT - 6, true);

            let time_str = if opts.display_seconds {
                format!("{}{}", hh_mm, sec_str)
            } else {
                hh_mm
            };
            draw_font(
                canvas,
                TtfFontId::DigiBig,
                64,
                11,
                &time_str,
                AlignH::Center,
                true,
            );
            if !opts.display_seconds {
                if let Some(ap) = am_pm {
                    let tw = measure_ttf(TtfFontId::DigiBig, &time_str);
                    draw_font(
                        canvas,
                        TtfFontId::Munro10,
                        (64 + tw / 2 + 8).min(116),
                        21,
                        ap,
                        AlignH::Center,
                        true,
                    );
                }
            }

            // 60-second progress bar along y=37..38
            let bar_w = ((now.second() as i32 + 1) * 108) / 60;
            canvas.draw_hline(10, 117, 38, true);
            canvas.fill_rect(10, 37, bar_w.clamp(2, 108), 2, true);
        }
    }

    if opts.style != ClockStyle::RightCalendar {
        if let Some(pct) = opts.battery_pct {
            draw_battery(canvas, OLED_WIDTH - 23, 2, pct, opts.show_battery_percent);
        }
    }
}
