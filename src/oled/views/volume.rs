use super::super::canvas::{Canvas128x40, OLED_WIDTH};
use super::super::fonts::{draw_font, AlignH, TtfFontId};
use super::super::icons::{
    ICON_MIC_OFF, ICON_MIC_ON, ICON_SPEAKER_HIGH, ICON_SPEAKER_LOW, ICON_SPEAKER_MID,
    ICON_SPEAKER_MUTE,
};

pub fn render_volume(
    canvas: &mut Canvas128x40,
    speaker_vol: u8,
    speaker_muted: bool,
    mic_muted: Option<bool>,
) {
    canvas.clear();

    // Left: Speaker icon + percentage
    let spk_icon = if speaker_muted || speaker_vol == 0 {
        ICON_SPEAKER_MUTE
    } else if speaker_vol < 33 {
        ICON_SPEAKER_LOW
    } else if speaker_vol < 66 {
        ICON_SPEAKER_MID
    } else {
        ICON_SPEAKER_HIGH
    };
    canvas.draw_bitmap(3, 10, spk_icon, true);
    let vol_lbl = if speaker_muted {
        "MUTE".to_string()
    } else {
        format!("{}%", speaker_vol.min(100))
    };
    draw_font(canvas, TtfFontId::Munro10, 9, 25, &vol_lbl, AlignH::Center, true);

    // Right: Mic icon + state badge (if mic available)
    let bar_x1 = 21;
    let bar_x2 = if let Some(muted) = mic_muted {
        let mic_icon = if muted { ICON_MIC_OFF } else { ICON_MIC_ON };
        canvas.draw_bitmap(OLED_WIDTH - 15, 10, mic_icon, true);
        draw_font(
            canvas,
            TtfFontId::Munro10,
            OLED_WIDTH - 2,
            25,
            if muted { "MUTE" } else { "LIVE" },
            AlignH::Right,
            true,
        );
        OLED_WIDTH - 21
    } else {
        OLED_WIDTH - 4
    };

    // Center: Sleek pill volume bar with 25/50/75% micro-ticks
    let bar_w = (bar_x2 - bar_x1).max(16);
    let bar_y = 14;
    let bar_h = 11;
    canvas.draw_rounded_rect(bar_x1, bar_y, bar_w, bar_h, true);

    if !speaker_muted && speaker_vol > 0 {
        let fill_w = ((bar_w - 4) as f32 * (speaker_vol.min(100) as f32 / 100.0)).round() as i32;
        if fill_w > 0 {
            canvas.fill_rect(bar_x1 + 2, bar_y + 2, fill_w, bar_h - 4, true);
        }
    }

    // Subtle ticks below the bar at 25%, 50%, 75%
    for frac in [0.25_f32, 0.50, 0.75] {
        let tx = bar_x1 + (bar_w as f32 * frac).round() as i32;
        canvas.draw_vline(tx, bar_y + bar_h + 1, bar_y + bar_h + 2, true);
    }
}
