use serde::{Deserialize, Serialize};

use super::super::canvas::{Canvas128x40, OLED_WIDTH};
use super::super::fonts::{draw_font, measure_ttf, AlignH, TtfFontId};
use super::super::icons::{
    ICON_MEDIA_16, ICON_MEDIA_18, ICON_SPOTIFY_16, ICON_SPOTIFY_18, ICON_YOUTUBE_16,
    ICON_YOUTUBE_18,
};
use super::super::scroll::ScrollText;

pub const SPECTRUM_BANDS: usize = 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PlayerStyle {
    ModernCard,
    CompactBar,
    CenteredStudio,
    SpectrumTicker,
    UltraMinimal,
}

impl Default for PlayerStyle {
    fn default() -> Self {
        Self::ModernCard
    }
}

impl PlayerStyle {
    pub const ALL: [PlayerStyle; 5] = [
        PlayerStyle::ModernCard,
        PlayerStyle::CompactBar,
        PlayerStyle::CenteredStudio,
        PlayerStyle::SpectrumTicker,
        PlayerStyle::UltraMinimal,
    ];

    pub fn label(self) -> &'static str {
        match self {
            PlayerStyle::ModernCard => "Modern Card",
            PlayerStyle::CompactBar => "Compact Bar",
            PlayerStyle::CenteredStudio => "Centered Studio",
            PlayerStyle::SpectrumTicker => "Spectrum Ticker",
            PlayerStyle::UltraMinimal => "Ultra Minimal",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MediaSource {
    Spotify,
    YouTube,
    Generic,
}

pub struct PlayerView {
    pub title_scroll: ScrollText,
    pub artist_scroll: ScrollText,
    pub combined_scroll: ScrollText,
    pub source: MediaSource,
    pub position_ms: u64,
    pub duration_ms: u64,
    pub paused: bool,
    pub step: u32,
    pub spectrum_bands: [f32; SPECTRUM_BANDS],
    pub spectrum_peaks: [f32; SPECTRUM_BANDS],
}

impl Default for PlayerView {
    fn default() -> Self {
        Self {
            title_scroll: ScrollText::new(20),
            artist_scroll: ScrollText::new(20),
            combined_scroll: ScrollText::new(15),
            source: MediaSource::Spotify,
            position_ms: 0,
            duration_ms: 1,
            paused: true,
            step: 0,
            spectrum_bands: [0.0; SPECTRUM_BANDS],
            spectrum_peaks: [0.0; SPECTRUM_BANDS],
        }
    }
}

impl PlayerView {
    pub fn update_track(
        &mut self,
        title: &str,
        artist: &str,
        position_ms: u64,
        duration_ms: u64,
        paused: bool,
        source: MediaSource,
    ) {
        self.title_scroll.set_text(title);
        self.artist_scroll.set_text(artist);
        let combined = if artist.trim().is_empty() {
            title.to_string()
        } else {
            format!("{}  -  {}", artist, title)
        };
        self.combined_scroll.set_text(&combined);
        self.position_ms = position_ms;
        self.duration_ms = duration_ms.max(1);
        self.paused = paused;
        self.source = source;
    }

    pub fn set_spectrum(&mut self, bands: [f32; SPECTRUM_BANDS], peaks: [f32; SPECTRUM_BANDS]) {
        self.spectrum_bands = bands;
        self.spectrum_peaks = peaks;
    }

    pub fn tick_scroll(&mut self) {
        self.step = self.step.wrapping_add(1);
        self.title_scroll.tick();
        self.artist_scroll.tick();
        self.combined_scroll.tick();
        if !self.paused && self.position_ms < self.duration_ms {
            self.position_ms = (self.position_ms + 100).min(self.duration_ms);
        }
    }

    fn icon_18(&self) -> &'static [&'static str] {
        match self.source {
            MediaSource::Spotify => ICON_SPOTIFY_18,
            MediaSource::YouTube => ICON_YOUTUBE_18,
            MediaSource::Generic => ICON_MEDIA_18,
        }
    }

    fn icon_16(&self) -> &'static [&'static str] {
        match self.source {
            MediaSource::Spotify => ICON_SPOTIFY_16,
            MediaSource::YouTube => ICON_YOUTUBE_16,
            MediaSource::Generic => ICON_MEDIA_16,
        }
    }

    fn fmt_time(ms: u64) -> String {
        let secs = ms / 1000;
        let h = secs / 3600;
        let m = (secs % 3600) / 60;
        let s = secs % 60;
        if h > 0 {
            format!("{}:{:02}:{:02}", h, m, s)
        } else {
            format!("{}:{:02}", m, s)
        }
    }

    fn progress_ratio(&self) -> f32 {
        if self.duration_ms == 0 {
            0.0
        } else {
            (self.position_ms as f32 / self.duration_ms as f32).clamp(0.0, 1.0)
        }
    }

    /// High-craft OLED scrub bar: optical-gray dotted unplayed rail, crisp solid played bar,
    /// micro end-ticks, and a sharp playhead pill with 1px knockout contrast.
    fn draw_scrub_bar(canvas: &mut Canvas128x40, x: i32, y: i32, w: i32, pct: f32, thick: bool) {
        if w < 10 {
            return;
        }
        let x1 = x + w - 1;
        // Micro end-ticks
        canvas.draw_vline(x, y - 1, y + 1, true);
        canvas.draw_vline(x1, y - 1, y + 1, true);

        // Optical-gray dotted unplayed rail
        for px in (x + 2..x1 - 1).step_by(2) {
            canvas.set_pixel(px, y, true);
        }

        // Played solid bar
        let usable = (w - 4).max(1);
        let knob_x = x + 2 + ((usable as f32) * pct).round() as i32;
        let bar_h = if thick { 3 } else { 2 };
        let bar_top = if thick { y - 1 } else { y };
        if knob_x > x + 1 {
            canvas.fill_rect(x + 1, bar_top, knob_x - (x + 1), bar_h, true);
        }

        // Knockout gap around playhead pill so it pops cleanly off the bar
        let kw = if thick { 4 } else { 3 };
        let kh = if thick { 7 } else { 5 };
        let ky = y - kh / 2;
        canvas.fill_rect(knob_x - 1, ky, kw + 2, kh, false);
        canvas.fill_rounded_rect(knob_x, ky, kw, kh, true);
    }

    fn draw_play_pause_micro(canvas: &mut Canvas128x40, cx: i32, y: i32, paused: bool) {
        if paused {
            canvas.fill_rect(cx - 2, y, 2, 5, true);
            canvas.fill_rect(cx + 1, y, 2, 5, true);
        } else {
            canvas.draw_vline(cx - 2, y, y + 4, true);
            canvas.draw_vline(cx - 1, y + 1, y + 3, true);
            canvas.set_pixel(cx, y + 2, true);
        }
    }

    pub fn render(&self, canvas: &mut Canvas128x40, style: PlayerStyle) {
        canvas.clear();
        let pct = self.progress_ratio();
        let pos_str = Self::fmt_time(self.position_ms);
        let dur_str = Self::fmt_time(self.duration_ms);

        match style {
            PlayerStyle::ModernCard => {
                // Standalone borderless source icon on left (no square box!)
                canvas.draw_bitmap(2, 2, self.icon_18(), true);

                // Right text column: clipped strictly to x=[24..126]
                self.title_scroll
                    .draw(canvas, TtfFontId::Verdana11, 24, 2, 102, 14, false);
                self.artist_scroll
                    .draw(canvas, TtfFontId::Munro10, 24, 16, 102, 24, false);

                // High-craft scrub bar + timestamps + micro play/pause glyph
                Self::draw_scrub_bar(canvas, 2, 27, OLED_WIDTH - 4, pct, false);
                draw_font(canvas, TtfFontId::Munro10, 2, 33, &pos_str, AlignH::Left, true);
                Self::draw_play_pause_micro(canvas, OLED_WIDTH / 2, 33, self.paused);
                draw_font(
                    canvas,
                    TtfFontId::Munro10,
                    OLED_WIDTH - 3,
                    33,
                    &dur_str,
                    AlignH::Right,
                    true,
                );
            }

            PlayerStyle::CompactBar => {
                // Top row: standalone 16x16 icon | scrolling title | M:SS/M:SS
                canvas.draw_bitmap(2, 4, self.icon_16(), true);
                let ts = format!("{}/{}", pos_str, dur_str);
                let ts_w = measure_ttf(TtfFontId::Munro10, &ts);
                let title_x = 22;
                let title_w = (OLED_WIDTH - title_x - ts_w - 6).max(20);
                self.title_scroll.draw(
                    canvas,
                    TtfFontId::Verdana11,
                    title_x,
                    7,
                    title_w,
                    25,
                    false,
                );
                draw_font(
                    canvas,
                    TtfFontId::Munro10,
                    OLED_WIDTH - 2,
                    9,
                    &ts,
                    AlignH::Right,
                    true,
                );

                // Thick high-craft scrub bar at bottom
                Self::draw_scrub_bar(canvas, 2, 31, OLED_WIDTH - 4, pct, true);
            }

            PlayerStyle::CenteredStudio => {
                // Minimal top accent rule with centered 3x3 diamond
                canvas.draw_hline(14, 58, 2, true);
                canvas.draw_hline(69, OLED_WIDTH - 15, 2, true);
                canvas.set_pixel(63, 1, true);
                canvas.fill_rect(62, 2, 3, 1, true);
                canvas.set_pixel(63, 3, true);

                // Centered full-width clipped Title + Artist
                self.title_scroll.draw(
                    canvas,
                    TtfFontId::Verdana11,
                    4,
                    6,
                    OLED_WIDTH - 8,
                    18,
                    true,
                );
                self.artist_scroll
                    .draw(canvas, TtfFontId::Munro10, 4, 20, OLED_WIDTH - 8, 28, true);

                // Bottom row: elapsed | high-craft scrub bar | total
                draw_font(canvas, TtfFontId::Munro10, 2, 32, &pos_str, AlignH::Left, true);
                draw_font(
                    canvas,
                    TtfFontId::Munro10,
                    OLED_WIDTH - 3,
                    32,
                    &dur_str,
                    AlignH::Right,
                    true,
                );
                Self::draw_scrub_bar(canvas, 26, 34, OLED_WIDTH - 52, pct, false);
            }

            PlayerStyle::SpectrumTicker => {
                // Wide edge-to-edge 20-band real-audio spectrum analyzer (x=5..123, y=1..18)
                let start_x = 5;
                let base_y = 18;
                let max_h = 17;
                for i in 0..SPECTRUM_BANDS {
                    let bx = start_x + (i as i32) * 6;
                    let level = self.spectrum_bands[i].clamp(0.0, 1.0);
                    let peak = self.spectrum_peaks[i].clamp(0.0, 1.0);
                    let bar_h = if self.paused {
                        1
                    } else {
                        ((level * max_h as f32).round() as i32).clamp(1, max_h)
                    };
                    canvas.fill_rect(bx, base_y - bar_h + 1, 4, bar_h, true);

                    // Floating 1px peak-hold cap
                    if !self.paused {
                        let peak_h = ((peak * max_h as f32).round() as i32).clamp(1, max_h);
                        let cap_y = (base_y - peak_h - 1).max(0);
                        if cap_y < base_y - bar_h {
                            canvas.draw_hline(bx, bx + 3, cap_y, true);
                        }
                    }
                }

                // Middle row: scrolling Artist - Title (left) + elapsed time (right)
                let ts_w = measure_ttf(TtfFontId::Munro10, &pos_str) + 4;
                self.combined_scroll.draw(
                    canvas,
                    TtfFontId::Munro10,
                    2,
                    23,
                    OLED_WIDTH - ts_w - 6,
                    31,
                    false,
                );
                draw_font(
                    canvas,
                    TtfFontId::Munro10,
                    OLED_WIDTH - 2,
                    23,
                    &pos_str,
                    AlignH::Right,
                    true,
                );

                // Bottom: high-craft scrub bar
                Self::draw_scrub_bar(canvas, 2, 35, OLED_WIDTH - 4, pct, false);
            }

            PlayerStyle::UltraMinimal => {
                // Refined 6px corner ticks around centered clipped Title & Artist
                canvas.draw_hline(2, 7, 2, true);
                canvas.draw_vline(2, 2, 7, true);
                canvas.draw_hline(OLED_WIDTH - 8, OLED_WIDTH - 3, 2, true);
                canvas.draw_vline(OLED_WIDTH - 3, 2, 7, true);
                canvas.draw_hline(2, 7, 29, true);
                canvas.draw_vline(2, 24, 29, true);
                canvas.draw_hline(OLED_WIDTH - 8, OLED_WIDTH - 3, 29, true);
                canvas.draw_vline(OLED_WIDTH - 3, 24, 29, true);

                self.title_scroll.draw(
                    canvas,
                    TtfFontId::Verdana11,
                    13,
                    5,
                    OLED_WIDTH - 26,
                    17,
                    true,
                );
                self.artist_scroll.draw(
                    canvas,
                    TtfFontId::Munro10,
                    13,
                    19,
                    OLED_WIDTH - 26,
                    29,
                    true,
                );

                Self::draw_scrub_bar(canvas, 4, 35, OLED_WIDTH - 8, pct, false);
            }
        }
    }
}
